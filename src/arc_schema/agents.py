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
from arc_schema.world_model import (
    DeclarativeWorldModel,
    WorldModelError,
    build_history_skeleton,
    merge_world_model_extension,
)


SYSTEM_COMMON = """You are controlling an ARC-AGI-3 environment.
Return one JSON object only. Never invent an action outside available_actions.
ACTION6, when legal, requires integer x/y data. Observations use row run-length
encoding: each frame_rle item contains value:count runs.
Action meanings must be inferred only from observed transitions; never assume
directional semantics from external game source code."""


class SpendBudgetExceeded(RuntimeError):
    """Raised before an API call when the configured reserve would cross the cap."""


def _accumulate_client_runtime(metrics: RunMetrics, client: ModelClient) -> None:
    stats = dict(getattr(client, "last_event_stats", {}) or {})
    metrics.codex_transport_reconnects += int(stats.get("transport_reconnects", 0))
    metrics.codex_https_fallbacks += int(stats.get("https_fallbacks", 0))
    metrics.codex_transport_timeouts += int(stats.get("transport_timeouts", 0))
    metrics.codex_turn_failures += int(stats.get("turn_failures", 0))
    metrics.codex_tool_failures += int(stats.get("tool_failures", 0))
    metrics.codex_post_completion_forced_exits += int(stats.get("post_completion_forced_exits", 0))


def _record_context_events(
    client: ModelClient,
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
) -> None:
    drain = getattr(client, "drain_context_events", None)
    if not callable(drain):
        return
    for payload in drain():
        reason = str(payload.get("reason", "unknown"))
        metrics.codex_context_checkpoints += 1
        metrics.codex_context_checkpoint_reasons[reason] = (
            metrics.codex_context_checkpoint_reasons.get(reason, 0) + 1
        )
        journal.append("codex_context_checkpoint", payload)


def _message_content(
    payload: dict[str, Any],
    vision_parts: list[dict[str, Any]] | None,
) -> str | list[dict[str, Any]]:
    if vision_parts is not None:
        # ``build_compact_context`` materializes its text before callers add
        # treatment-specific instructions.  Refresh that text so vision runs
        # receive the same protocol constraints as non-vision runs while
        # retaining the already-rendered image part.
        refreshed = [dict(part) for part in vision_parts]
        refreshed[0] = {
            "type": "text",
            "text": (
                "Current frame as PNG. Use it together with the JSON context. "
                + canonical_json(payload)
            ),
        }
        return refreshed
    return canonical_json(payload)


def _record_call(
    client: ModelClient,
    messages: list[dict[str, Any]],
    purpose: str,
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    *,
    max_model_calls: int,
    max_spend_usd: float = 0.0,
    spend_reserve_usd: float = 0.0,
) -> ModelResponse:
    if metrics.model_calls >= max_model_calls:
        raise RuntimeError(f"model call budget exhausted ({max_model_calls})")
    spent = metrics.usage.estimated_cost_usd or 0.0
    if max_spend_usd > 0 and spent + max(0.0, spend_reserve_usd) > max_spend_usd:
        raise SpendBudgetExceeded(
            f"request reserve would cross spend cap: "
            f"spent={spent:.6f}, reserve={spend_reserve_usd:.6f}, cap={max_spend_usd:.6f}"
        )
    metrics.model_calls += 1
    journal.append("model_request", {"purpose": purpose, "messages": messages})
    try:
        response = client.complete_json(messages, purpose)
    except Exception as exc:
        _accumulate_client_runtime(metrics, client)
        _record_context_events(client, journal, metrics)
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
    _accumulate_client_runtime(metrics, client)
    metrics.model_api_attempts += response.attempts
    metrics.usage.add(response.usage)
    metrics.max_codex_prompt_tokens_per_turn = max(
        metrics.max_codex_prompt_tokens_per_turn,
        int(response.usage.prompt_tokens),
    )
    _record_context_events(client, journal, metrics)
    journal.append(
        "model_response",
        {
            "purpose": purpose,
            "raw_text": response.raw_text,
            "parsed": response.value,
            "usage": asdict(response.usage),
            "latency_seconds": response.latency_seconds,
            "api_attempts": response.attempts,
            "reasoning_text": getattr(response, "reasoning_text", None),
            "reasoning_status": getattr(response, "reasoning_status", "absent"),
            "reasoning_tokens": int(getattr(response.usage, "reasoning_tokens", 0) or 0),
            "model_thread_id": getattr(client, "thread_id", None),
            "context_policy": getattr(client, "context_policy", None),
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
            "Prefer untried_action_ids when exploration is still useful. "
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
                max_spend_usd=self.config.max_spend_usd,
                spend_reserve_usd=self.config.request_spend_reserve_usd,
            ).value
            action_value = value["action"]
            action = Action(id=int(action_value["id"]), data=dict(action_value.get("data", {})))
        except SpendBudgetExceeded:
            raise
        except Exception as exc:
            if getattr(self.client, "last_failure_kind", None) in {
                "infrastructure_error",
                "protocol_error",
            }:
                raise
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

    def choose_action_batch(
        self,
        current: Observation,
        history: list[Transition],
        journal: AppendOnlyJournal,
        metrics: RunMetrics,
    ) -> list[Action]:
        """Choose a strict no-harness batch for open-loop sequential execution."""
        max_batch = self.config.baseline_max_batch_actions
        if not 2 <= max_batch <= 16:
            raise ValueError("batched baseline requires a batch limit between 2 and 16")
        remaining_actions = self.config.max_environment_actions - metrics.environment_actions
        offered_batch = min(max_batch, remaining_actions)
        if offered_batch <= 0:
            raise RuntimeError("no environment action budget remains")

        payload, vision_parts = build_compact_context(
            current,
            history,
            limit=self.config.model.context_transitions,
            vision_enabled=self.config.model.vision_enabled,
        )
        payload["batch_constraints"] = {
            "minimum_actions": 1,
            "maximum_actions": offered_batch,
            "execution": "sequential_open_loop_without_observation_feedback",
            "automatic_stop_conditions": [
                "level_boundary",
                "GAME_OVER_or_WIN",
                "environment_action_budget",
                "wall_clock_or_resource_budget",
            ],
            "reset_action_zero_forbidden": True,
        }
        payload["instruction"] = (
            "Choose between 1 and maximum_actions real-environment actions. "
            "Batch a coherent sequence when confidence is high; return only one action "
            "when observation feedback is needed. Every id must be currently legal. "
            'Schema: {"actions":[{"id":1,"data":{}}]}.'
        )
        messages = [
            {
                "role": "system",
                "content": SYSTEM_COMMON
                + "\nThis is a strict direct-action baseline: do not construct or search "
                "an executable world model and do not use external persistent artifacts. "
                f"You may return a short open-loop batch of 1 to {offered_batch} actions.",
            },
            {"role": "user", "content": _message_content(payload, vision_parts)},
        ]
        value = _record_call(
            self.client,
            messages,
            "baseline_action",
            journal,
            metrics,
            max_model_calls=self.config.max_model_calls_per_run,
            max_spend_usd=self.config.max_spend_usd,
            spend_reserve_usd=self.config.request_spend_reserve_usd,
        ).value
        if not isinstance(value, dict) or set(value) != {"actions"}:
            raise ValueError("batched baseline must return only the top-level 'actions' key")
        raw_actions = value["actions"]
        if not isinstance(raw_actions, list) or not 1 <= len(raw_actions) <= offered_batch:
            raise ValueError(f"batched baseline must return 1..{offered_batch} actions")

        actions: list[Action] = []
        for index, item in enumerate(raw_actions):
            if not isinstance(item, dict) or "id" not in item:
                raise ValueError(f"batched baseline action {index} must contain an id")
            if set(item) - {"id", "data"}:
                raise ValueError(f"batched baseline action {index} has unknown keys")
            data = item.get("data", {})
            if not isinstance(data, dict):
                raise ValueError(f"batched baseline action {index} data must be an object")
            action = Action(id=int(item["id"]), data=dict(data))
            if action.id == 0:
                raise ValueError("batched baseline may not submit RESET(0)")
            if action.id not in current.available_actions:
                raise ValueError(f"batched baseline selected initially illegal action {action.id}")
            actions.append(action)
        return actions


@dataclass(frozen=True)
class HarnessPlan:
    model: DeclarativeWorldModel | None
    steps: list[PlannedStep]
    backtest: BacktestResult | None
    reason: str


class FsmHarnessAgent:
    """Legacy declarative-FSM harness retained as an ablation (harness_mode=fsm)."""

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
        context_limit = self.config.model.context_transitions
        known_levels = max(
            [current.levels_completed, *[item.after.levels_completed for item in history]],
            default=current.levels_completed,
        )
        skeleton = build_history_skeleton(current, history, limit=context_limit)
        for _ in range(self.config.harness_model_attempts):
            payload, vision_parts = build_compact_context(
                current,
                history,
                limit=context_limit,
                vision_enabled=self.config.model.vision_enabled,
            )
            catalog = local_observation_catalog(
                current,
                history,
                limit=context_limit,
            )
            payload["known_snapshot_refs"] = sorted(catalog)
            payload["seeded_world_model"] = {
                "states": skeleton["states"],
                "transitions": skeleton["transitions"],
                "current_state_id": skeleton["current_state_id"],
            }
            payload["previous_failure"] = feedback
            payload["instruction"] = (
                "seeded_world_model already covers the observed history window with "
                "snapshot_ref states and historical transitions. Do NOT restate that "
                "history. Return extensions only: hypothesized future states must use "
                "base_ref + sparse snapshot_patch (changed rows/metadata only); never "
                "copy a full frame. Add new legal outgoing transitions from the current "
                f"seeded state ({skeleton['current_state_id']}) toward a reachable goal "
                f"within {self.config.max_plan_steps} steps. A goal MUST set "
                f"levels_completed>={known_levels + 1} or state=WIN; never mark ordinary "
                "intermediate frames as goals. Keep the merged model within 24 states "
                "and 64 transitions. Schema: "
                '{"states":[{"id":"g0","base_ref":"obs_...","snapshot_patch":'
                '{"rows":[{"y":0,"rle":"..."}],"metadata":{"state":"NOT_FINISHED",'
                f'"levels_completed":{known_levels + 1}'
                "}},"
                '"goal":true}],'
                '"transitions":[{"from":"h0","action":{"id":1,"data":{}},"to":"g0"}],'
                '"goal_state_ids":["g0"]}.'
            )
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_COMMON
                    + "\nYour output is interpreted only as a declarative finite-state model "
                    "extension. It is merged onto the seeded history model, materialized, "
                    "and replayed before any planning is allowed.",
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
                    max_spend_usd=self.config.max_spend_usd,
                    spend_reserve_usd=self.config.request_spend_reserve_usd,
                ).value
                merged = merge_world_model_extension(skeleton, value)
                model = DeclarativeWorldModel.from_dict(
                    merged,
                    catalog=catalog,
                    known_levels=known_levels,
                )
            except (WorldModelError, ValueError, RuntimeError) as exc:
                metrics.backtest_failures += 1
                feedback = {"reason": f"invalid world model: {exc}"}
                journal.append("backtest_failed", feedback)
                continue
            result = backtest(model, history, limit=context_limit)
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
            if not model.goal_state_ids():
                metrics.backtest_failures += 1
                feedback = {"reason": "world model has no goal state"}
                journal.append("backtest_failed", feedback)
                continue
            invalid_goals = []
            for goal_id in sorted(model.goal_state_ids()):
                snap = model.states[goal_id].snapshot
                advanced = int(snap.get("levels_completed", 0)) > known_levels
                won = str(snap.get("state", "")) == "WIN"
                if not (advanced or won):
                    invalid_goals.append(goal_id)
            if invalid_goals:
                metrics.backtest_failures += 1
                feedback = {
                    "reason": (
                        "goal states must increase levels_completed or be WIN; "
                        f"invalid={invalid_goals}"
                    )
                }
                journal.append("backtest_failed", feedback)
                continue
            if not list(model.outgoing(start.id)):
                metrics.backtest_failures += 1
                feedback = {"reason": "current state has no outgoing transitions"}
                journal.append("backtest_failed", feedback)
                continue
            steps = bfs_plan(
                model,
                start.id,
                self.config.planner_max_nodes,
                max_depth=self.config.max_plan_steps,
            )
            if steps is None:
                metrics.backtest_failures += 1
                feedback = {"reason": "no path from current state to a goal within max_plan_steps"}
                journal.append("backtest_failed", feedback)
                continue
            if not steps:
                return HarnessPlan(model, [], result, "already_at_goal")
            return HarnessPlan(model, steps[: self.config.max_plan_steps], result, "planned")
        return HarnessPlan(None, [], last_backtest, "backtest_failed")


class SchemaHarnessAgent:
    """Schema-aligned harness: deliberation tools + program world model + commit_actions."""

    name = "harness"

    def __init__(self, client: ModelClient, config: ExperimentConfig) -> None:
        self.client = client
        self.config = config
        self.workspace = None  # set by runner with run directory

    def bind_workspace(self, workspace) -> None:
        self.workspace = workspace
        bind = getattr(self.client, "bind_workspace", None)
        if callable(bind):
            bind(workspace)


def make_harness_agent(client: ModelClient, config: ExperimentConfig):
    if config.harness_mode == "fsm":
        return FsmHarnessAgent(client, config)
    return SchemaHarnessAgent(client, config)


# Backward-compatible name used by older tests that construct the FSM agent directly.
HarnessAgent = FsmHarnessAgent
