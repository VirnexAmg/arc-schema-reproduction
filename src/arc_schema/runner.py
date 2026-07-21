from __future__ import annotations

import time
from pathlib import Path

from arc_schema.agents import BaselineAgent, HarnessAgent, choose_fallback_action
from arc_schema.config import ExperimentConfig
from arc_schema.core import Action, RunMetrics, Transition, canonical_json
from arc_schema.environment import Environment
from arc_schema.history import AppendOnlyJournal


def run_agent(
    agent: BaselineAgent | HarnessAgent,
    environment: Environment,
    config: ExperimentConfig,
    run_index: int,
    seed: int,
    journal_path: Path,
) -> RunMetrics:
    journal = AppendOnlyJournal(journal_path)
    metrics = RunMetrics(
        agent=agent.name,
        game_id=config.game_id,
        run_index=run_index,
        seed=seed,
    )
    history: list[Transition] = []
    started = time.monotonic()
    journal.append(
        "run_started",
        {
            "agent": agent.name,
            "run_index": run_index,
            "seed": seed,
            "config": config.public_dict(),
        },
    )
    journal.append("observation", {"kind": "initial", **environment.current.to_dict()})
    try:
        if isinstance(agent, BaselineAgent):
            _run_baseline(agent, environment, config, history, journal, metrics, started)
        else:
            _run_harness(agent, environment, config, history, journal, metrics, started)
        if metrics.status == "running":
            metrics.status = (
                environment.current.state.lower()
                if environment.current.terminal
                else "action_budget_exhausted"
            )
    except Exception as exc:
        metrics.status = "failed"
        metrics.error = f"{type(exc).__name__}: {exc}"
        journal.append("run_error", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        try:
            summary = environment.score_summary()
        except Exception as exc:
            summary = {}
            metrics.status = "failed"
            suffix = f"{type(exc).__name__}: {exc}"
            metrics.error = f"{metrics.error}; scorecard: {suffix}" if metrics.error else suffix
            journal.append("scorecard_error", {"type": type(exc).__name__, "message": str(exc)})
        metrics.score = float(summary.get("score", 0.0))
        metrics.levels_completed = int(
            summary.get("levels_completed", environment.current.levels_completed)
        )
        metrics.win_levels = environment.current.win_levels
        metrics.completed = bool(summary.get("completed", environment.current.state == "WIN"))
        metrics.wall_clock_seconds = time.monotonic() - started
        journal.append("run_finished", metrics.to_dict())
    return metrics


def _budget_ok(
    metrics: RunMetrics,
    environment: Environment,
    config: ExperimentConfig,
    started: float,
) -> bool:
    if environment.current.terminal:
        return False
    if metrics.environment_actions >= config.max_environment_actions:
        return False
    if time.monotonic() - started >= config.run_timeout_seconds:
        metrics.status = "timeout"
        return False
    return True


def _apply_action(
    environment: Environment,
    action: Action,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    *,
    kind: str,
) -> Transition:
    before = environment.current
    after = environment.step(action)
    metrics.environment_actions += 1
    if kind == "exploration":
        metrics.exploration_actions += 1
    elif kind == "planned":
        metrics.planned_actions += 1
    transition = Transition(before, action, after)
    history.append(transition)
    journal.append("transition", {**transition.to_dict(), "kind": kind})
    return transition


def _run_baseline(
    agent: BaselineAgent,
    environment: Environment,
    config: ExperimentConfig,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    started: float,
) -> None:
    while _budget_ok(metrics, environment, config, started):
        before = environment.current
        fallback_before = metrics.fallback_actions
        action = agent.choose_action(before, history, journal, metrics)
        kind = "fallback" if metrics.fallback_actions > fallback_before else "baseline"
        _apply_action(environment, action, history, journal, metrics, kind=kind)


def _explore_once(
    agent: HarnessAgent,
    environment: Environment,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
) -> bool:
    action = agent.explore_action(environment.current, history)
    if action is None:
        action = choose_fallback_action(environment.current, history)
        if action is None:
            return False
        metrics.fallback_actions += 1
        journal.append(
            "fallback_action",
            {"reason": "no explore candidate", "action": {"id": action.id, "data": action.data}},
        )
    _apply_action(environment, action, history, journal, metrics, kind="exploration")
    return True


def _run_harness(
    agent: HarnessAgent,
    environment: Environment,
    config: ExperimentConfig,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    started: float,
) -> None:
    while _budget_ok(metrics, environment, config, started):
        if metrics.exploration_actions < config.explore_steps:
            if not _explore_once(agent, environment, history, journal, metrics):
                metrics.status = "no_legal_action"
                return
            continue

        plan = agent.build_plan(environment.current, history, journal, metrics)
        journal.append(
            "plan",
            {
                "reason": plan.reason,
                "steps": [
                    {
                        "action": {"id": step.action.id, "data": step.action.data},
                        "predicted_state_id": step.predicted_state_id,
                    }
                    for step in plan.steps
                ],
            },
        )
        if plan.reason != "planned" or plan.model is None:
            # Retreat to one explore step instead of ending the episode.
            if not _explore_once(agent, environment, history, journal, metrics):
                metrics.status = plan.reason
                return
            continue

        matched_any = False
        for step in plan.steps:
            if not _budget_ok(metrics, environment, config, started):
                return
            if step.action.id not in environment.current.available_actions:
                metrics.prediction_mismatches += 1
                journal.append(
                    "prediction_mismatch",
                    {
                        "reason": "planned action is no longer legal",
                        "action_id": step.action.id,
                    },
                )
                break
            transition = _apply_action(
                environment,
                step.action,
                history,
                journal,
                metrics,
                kind="planned",
            )
            predicted = plan.model.states[step.predicted_state_id].snapshot
            actual = transition.after.snapshot()
            if canonical_json(predicted) != canonical_json(actual):
                metrics.prediction_mismatches += 1
                journal.append(
                    "prediction_mismatch",
                    {
                        "reason": "predicted state differs from real observation",
                        "predicted": predicted,
                        "actual": actual,
                    },
                )
                break
            matched_any = True
            journal.append(
                "prediction_matched",
                {"predicted_state_id": step.predicted_state_id},
            )
        else:
            # Entire short plan matched; continue with another plan next loop.
            continue

        # Mismatch or illegal planned action: explore once, then replan.
        if not matched_any or metrics.prediction_mismatches:
            if _budget_ok(metrics, environment, config, started):
                _explore_once(agent, environment, history, journal, metrics)
