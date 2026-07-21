from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from arc_schema.backtest import BacktestResult, backtest
from arc_schema.config import ExperimentConfig
from arc_schema.context import (
    build_compact_context,
    local_observation_catalog,
    next_explore_action,
)
from arc_schema.core import Action, Observation, RunMetrics, Transition, canonical_json
from arc_schema.deepseek_client import ModelClient, ModelResponse
from arc_schema.history import AppendOnlyJournal
from arc_schema.planner import PlannedStep, bfs_plan
from arc_schema.world_model import DeclarativeWorldModel, WorldModelError


SYSTEM_COMMON = """You are controlling an ARC-AGI-3 environment.
Return one JSON object only. Never invent an action outside available_actions.
ACTION6, when legal, requires integer x/y data. Observations use row run-length
encoding: each frame_rle item contains value:count runs.
Action meanings must be inferred only from observed transitions; never assume
directional semantics from external game source code."""


def _message_content(
    payload: dict[str, Any],
    vision_parts: list[dict[str, Any]] | None,
) -> str | list[dict[str, Any]]:
    if vision_parts is not None:
        return vision_parts
    return canonical_json(payload)


def _record_call(
    client: ModelClient,
    messages: list[dict[str, Any]],
    purpose: str,
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    *,
    max_model_calls: int,
) -> ModelResponse:
    if metrics.model_calls >= max_model_calls:
        raise RuntimeError(f"model call budget exhausted ({max_model_calls})")
    metrics.model_calls += 1
    journal.append("model_request", {"purpose": purpose, "messages": messages})
    try:
        response = client.complete_json(messages, purpose)
    except Exception as exc:
        metrics.model_failures += 1
        metrics.model_api_attempts += int(getattr(exc, "attempts", 0))
        error_usage = getattr(exc, "usage", None)
        if error_usage is not None:
            metrics.usage.add(error_usage)
        journal.append(
            "model_error",
            {
                "purpose": purpose,
                "type": type(exc).__name__,
                "message": str(exc),
                "api_attempts": int(getattr(exc, "attempts", 0)),
                "finish_reason": getattr(exc, "finish_reason", None),
                "raw_text": getattr(exc, "raw_text", ""),
                "usage": asdict(error_usage) if error_usage is not None else None,
            },
        )
        raise
    metrics.model_api_attempts += response.attempts
    metrics.usage.add(response.usage)
    journal.append(
        "model_response",
        {
            "purpose": purpose,
            "raw_text": response.raw_text,
            "parsed": response.value,
            "usage": asdict(response.usage),
            "latency_seconds": response.latency_seconds,
            "api_attempts": response.attempts,
        },
    )
    return response


def choose_fallback_action(current: Observation, history: list[Transition]) -> Action | None:
    explore = next_explore_action(current, history)
    if explore is not None:
        return explore
    if current.available_actions:
        return Action(id=current.available_actions[0])
    return None


class BaselineAgent:
    name = "baseline"

    def __init__(self, client: ModelClient, config: ExperimentConfig) -> None:
        self.client = client
        self.config = config

    def choose_action(
        self,
        current: Observation,
        history: list[Transition],
        journal: AppendOnlyJournal,
        metrics: RunMetrics,
    ) -> Action:
        payload, vision_parts = build_compact_context(
            current,
            history,
            limit=self.config.model.context_transitions,
            vision_enabled=self.config.model.vision_enabled,
        )
        payload["instruction"] = (
            "Choose exactly one next real-environment action. "
            'Prefer untried_action_ids when exploration is still useful. '
            'Schema: {"action":{"id":1,"data":{}}}.'
        )
        messages = [
            {
                "role": "system",
                "content": SYSTEM_COMMON
                + "\nYou may reason from history but may not construct or search an executable "
                "world model and may not return a multi-action plan.",
            },
            {"role": "user", "content": _message_content(payload, vision_parts)},
        ]
        try:
            value = _record_call(
                self.client,
                messages,
                "baseline_action",
                journal,
                metrics,
                max_model_calls=self.config.max_model_calls_per_run,
            ).value
            action_value = value["action"]
            action = Action(id=int(action_value["id"]), data=dict(action_value.get("data", {})))
        except Exception as exc:
            fallback = choose_fallback_action(current, history)
            if fallback is None:
                raise
            metrics.fallback_actions += 1
            journal.append(
                "fallback_action",
                {
                    "reason": f"{type(exc).__name__}: {exc}",
                    "action": asdict(fallback),
                },
            )
            return fallback
        if action.id not in current.available_actions:
            fallback = choose_fallback_action(current, history)
            if fallback is None:
                raise ValueError(f"model selected illegal action {action.id}")
            metrics.fallback_actions += 1
            journal.append(
                "fallback_action",
                {
                    "reason": f"illegal action {action.id}",
                    "action": asdict(fallback),
                },
            )
            return fallback
        return action


@dataclass(frozen=True)
class HarnessPlan:
    model: DeclarativeWorldModel | None
    steps: list[PlannedStep]
    backtest: BacktestResult | None
    reason: str


class HarnessAgent:
    name = "harness"

    def __init__(self, client: ModelClient, config: ExperimentConfig) -> None:
        self.client = client
        self.config = config

    def explore_action(
        self,
        current: Observation,
        history: list[Transition],
    ) -> Action | None:
        return next_explore_action(current, history)

    def build_plan(
        self,
        current: Observation,
        history: list[Transition],
        journal: AppendOnlyJournal,
        metrics: RunMetrics,
    ) -> HarnessPlan:
        feedback: dict[str, Any] | None = None
        last_backtest: BacktestResult | None = None
        known_levels = max(
            [current.levels_completed, *[item.after.levels_completed for item in history]],
            default=current.levels_completed,
        )
        for _ in range(self.config.harness_model_attempts):
            payload, vision_parts = build_compact_context(
                current,
                history,
                limit=self.config.model.context_transitions,
                vision_enabled=self.config.model.vision_enabled,
            )
            catalog = local_observation_catalog(
                current,
                history,
                limit=self.config.model.context_transitions,
            )
            payload["known_snapshot_refs"] = sorted(catalog)
            payload["previous_failure"] = feedback
            payload["instruction"] = (
                "Build a short deterministic finite-state world model. Known observations must "
                "use snapshot_ref only (see known_snapshot_refs / history before_ref/after_ref). "
                "Hypothesized future states must use base_ref + snapshot_patch with sparse "
                "changed rows and metadata; never copy a full frame and never raise "
                "levels_completed without evidence. Keep at most 24 states and 64 transitions. "
                "Include at least one legal outgoing transition from the current state and a "
                "reachable goal. Schema: "
                '{"states":[{"id":"s0","snapshot_ref":"obs_...","goal":false},'
                '{"id":"s1","base_ref":"obs_...","snapshot_patch":{"rows":[{"y":0,"rle":"..."}],'
                '"metadata":{"state":"NOT_FINISHED"}},"goal":true}],'
                '"transitions":[{"from":"s0","action":{"id":1,"data":{}},"to":"s1"}]}.'
            )
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_COMMON
                    + "\nYour output is interpreted only as a declarative finite-state model. "
                    "It will be materialized and replayed before any planning is allowed.",
                },
                {"role": "user", "content": _message_content(payload, vision_parts)},
            ]
            try:
                value = _record_call(
                    self.client,
                    messages,
                    "world_model",
                    journal,
                    metrics,
                    max_model_calls=self.config.max_model_calls_per_run,
                ).value
                model = DeclarativeWorldModel.from_dict(
                    value,
                    catalog=catalog,
                    known_levels=known_levels,
                )
            except (WorldModelError, ValueError, RuntimeError) as exc:
                metrics.backtest_failures += 1
                feedback = {"reason": f"invalid world model: {exc}"}
                journal.append("backtest_failed", feedback)
                continue
            result = backtest(model, history)
            last_backtest = result
            journal.append("backtest", asdict(result))
            if not result.passed:
                metrics.backtest_failures += 1
                feedback = asdict(result)
                continue
            start = model.state_for_observation(current)
            if start is None:
                metrics.backtest_failures += 1
                feedback = {"reason": "current observation is absent from world model"}
                journal.append("backtest_failed", feedback)
                continue
            steps = bfs_plan(
                model,
                start.id,
                self.config.planner_max_nodes,
                max_depth=self.config.max_plan_steps,
            )
            if steps is None:
                return HarnessPlan(model, [], result, "no_plan")
            if not steps:
                return HarnessPlan(model, [], result, "already_at_goal")
            return HarnessPlan(model, steps[: self.config.max_plan_steps], result, "planned")
        return HarnessPlan(None, [], last_backtest, "backtest_failed")
