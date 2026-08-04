from __future__ import annotations

"""
实验外环：驱动 agent 与真实环境交互，记录 journal / metrics。

本模块是 harness 的「执行壳」，按 agent 类型分派三条路径：
1. BaselineAgent：每步直接选动作并执行；
2. FsmHarnessAgent：先探索，再声明式世界模型规划，预测不一致则短 burst 再探索；
3. SchemaHarnessAgent：创建 Workspace，跑 DeliberationSession 内环，仅执行 commit 的动作，
   并对 planned/navigation 做 prequential 预测核对。

阅读导引（当前主线优先读）：
- run_agent：一次 run 总入口（建 journal → 分派 → scorecard → run_finished）
- _budget_ok：终局 / 目标关卡 / 动作上限 / 墙钟 / token·notional 是否仍允许继续
- _run_schema_harness：审议 → 接受 commit → 逐步预测→step→校验（唯一环境提交门）
- _apply_action：真实 env.step + Timeline + 分类动作计数

暂时可跳过：_run_baseline、_run_fsm_harness（旧路径 / 对照）。
"""

import time
from pathlib import Path

from arc_schema.agents import (
    BaselineAgent,
    FsmHarnessAgent,
    SchemaHarnessAgent,
    SpendBudgetExceeded,
    choose_fallback_action,
)
from arc_schema.config import ExperimentConfig
from arc_schema.context import next_explore_action
from arc_schema.core import (
    Action,
    RunMetrics,
    Transition,
    canonical_json,
    usage_budget_reason,
)
from arc_schema.deliberation import DeliberationSession
from arc_schema.environment import Environment
from arc_schema.history import AppendOnlyJournal
from arc_schema.program_world_model import (
    ProgramPrediction,
    ProgramRuntimeState,
    prediction_match_quality,
    prediction_mismatch_summary,
)
from arc_schema.workspace import Workspace


def run_agent(
    agent: BaselineAgent | FsmHarnessAgent | SchemaHarnessAgent,
    environment: Environment,
    config: ExperimentConfig,
    run_index: int,
    seed: int,
    journal_path: Path,
) -> RunMetrics:
    """跑完一次实验：初始化 journal/metrics，分派 agent 循环，最后写 scorecard 与收尾。"""
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
            bind_runtime = getattr(agent.client, "bind_workspace_path", None)
            if callable(bind_runtime):
                bind_runtime(journal_path.parent / f"workspace-baseline-{run_index}")
            _run_baseline(agent, environment, config, history, journal, metrics, started)
        elif isinstance(agent, SchemaHarnessAgent):
            workspace = Workspace(journal_path.parent / f"workspace-harness-{run_index}")
            agent.bind_workspace(workspace)
            _run_schema_harness(
                agent, environment, config, history, journal, metrics, started, workspace
            )
        else:
            _run_fsm_harness(agent, environment, config, history, journal, metrics, started)
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
        if isinstance(agent, SchemaHarnessAgent) and agent.workspace is not None:
            _write_trace_index(journal_path, agent.workspace, metrics)
    return metrics


def _budget_ok(
    metrics: RunMetrics,
    environment: Environment,
    config: ExperimentConfig,
    started: float,
) -> bool:
    """是否还能继续与环境交互：未终局（或可自动 RESET）、未超动作上限、未超墙钟超时。"""
    spent = metrics.usage.estimated_cost_usd or 0.0
    if (
        config.target_levels_completed > 0
        and environment.current.levels_completed >= config.target_levels_completed
    ):
        metrics.status = "target_levels_reached"
        return False
    resource_stop = usage_budget_reason(
        metrics.usage,
        max_total_tokens=config.max_total_tokens_per_run,
        max_uncached_tokens=config.max_uncached_tokens_per_run,
        max_output_tokens=config.max_output_tokens_per_run,
        max_notional_cost_usd=config.max_notional_cost_usd,
    )
    if resource_stop is not None:
        metrics.status = resource_stop
        return False
    if config.max_spend_usd > 0 and spent >= config.max_spend_usd:
        metrics.status = "spend_budget"
        return False
    if environment.current.terminal:
        # WIN ends the run; GAME_OVER may be cleared by auto-reset inside the loop.
        if environment.current.state == "WIN":
            return False
        if environment.current.state == "GAME_OVER" and config.auto_reset_on_game_over:
            if metrics.game_over_resets >= config.max_game_over_resets:
                return False
            # Still "ok" so the loop can issue RESET; action budget still applies after.
        else:
            return False
    if metrics.environment_actions >= config.max_environment_actions:
        return False
    if time.monotonic() - started >= config.run_timeout_seconds:
        metrics.status = "timeout"
        return False
    return True


def _maybe_auto_reset(
    environment: Environment,
    config: ExperimentConfig,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    workspace: Workspace | None = None,
) -> bool:
    """若处于 GAME_OVER 且允许自动续命，则执行 RESET(0)，保留 Timeline 与 workspace。

    返回 True 表示刚完成一次 reset（调用方应 continue 外环）。
    """
    if not config.auto_reset_on_game_over:
        return False
    if environment.current.state != "GAME_OVER":
        return False
    if metrics.environment_actions >= config.max_environment_actions:
        return False
    if metrics.game_over_resets >= config.max_game_over_resets:
        metrics.status = "game_over"
        journal.append(
            "reset_budget_exhausted",
            {
                "game_over_resets": metrics.game_over_resets,
                "max_game_over_resets": config.max_game_over_resets,
            },
        )
        return False

    before = environment.current
    action = Action(id=0)  # GameAction.RESET
    after = environment.step(action)
    metrics.environment_actions += 1
    metrics.game_over_resets += 1
    transition = Transition(before, action, after)
    history.append(transition)
    journal.append(
        "life_reset",
        {
            "kind": "reset",
            "reset_index": metrics.game_over_resets,
            "levels_completed_before": before.levels_completed,
            "state_after": after.state,
            "levels_completed_after": after.levels_completed,
            "note": "Timeline and workspace preserved; re-certify world model before planning",
            **transition.to_dict(),
        },
    )
    if workspace is not None:
        workspace.last_backtest = None
        workspace.record_boundary(
            {
                "reason": "life_reset_after_game_over",
                "reset_index": metrics.game_over_resets,
                "message": (
                    "Episode died. Prior transitions remain in the Timeline. "
                    "Run backtest on the FULL history before planning again."
                ),
            },
            reason="life_reset",
        )
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
    """在真实环境执行一步，更新 metrics / history / journal，返回 Transition。"""
    before = environment.current
    after = environment.step(action)
    metrics.environment_actions += 1
    if kind == "exploration":
        metrics.exploration_actions += 1
    elif kind == "navigation":
        metrics.navigation_actions += 1
    elif kind == "planned":
        metrics.planned_actions += 1
    transition = Transition(before, action, after)
    history.append(transition)
    journal.append("transition", {**transition.to_dict(), "kind": kind})
    metrics.levels_completed = after.levels_completed
    if after.levels_completed > before.levels_completed:
        checkpoint = {
            "level": after.levels_completed,
            "environment_actions": metrics.environment_actions,
            "model_calls": metrics.model_calls,
            "prompt_tokens": metrics.usage.prompt_tokens,
            "cached_prompt_tokens": metrics.usage.cached_prompt_tokens,
            "completion_tokens": metrics.usage.completion_tokens,
            "reasoning_tokens": metrics.usage.reasoning_tokens,
            "total_tokens": metrics.usage.total_tokens,
            "estimated_cost_usd": metrics.usage.estimated_cost_usd,
        }
        metrics.level_checkpoints.append(checkpoint)
        journal.append("level_resource_checkpoint", checkpoint)
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
    """基线循环：每步由 agent 选动作并执行，直至预算耗尽。"""
    while _budget_ok(metrics, environment, config, started):
        if _maybe_auto_reset(environment, config, history, journal, metrics):
            continue
        if metrics.model_calls >= config.max_model_calls_per_run:
            metrics.status = "model_call_budget"
            metrics.model_budget_exhausted_at_action = metrics.environment_actions
            journal.append(
                "model_call_budget",
                {
                    "model_calls": metrics.model_calls,
                    "max_model_calls": config.max_model_calls_per_run,
                    "environment_actions": metrics.environment_actions,
                },
            )
            return
        resource_stop = usage_budget_reason(
            metrics.usage,
            max_total_tokens=config.max_total_tokens_per_run,
            max_uncached_tokens=config.max_uncached_tokens_per_run,
            max_output_tokens=config.max_output_tokens_per_run,
            max_notional_cost_usd=config.max_notional_cost_usd,
            total_token_reserve=config.token_reserve_per_call,
        )
        if resource_stop is not None:
            metrics.status = resource_stop
            journal.append(
                "resource_budget",
                {
                    "reason": resource_stop,
                    "environment_actions": metrics.environment_actions,
                    "model_calls": metrics.model_calls,
                },
            )
            return
        begin = getattr(agent.client, "begin_deliberation", None)
        if callable(begin):
            rollover = begin()
            if rollover is not None:
                metrics.codex_session_rollovers += 1
                journal.append(
                    "codex_session_rollover",
                    {"env_step": metrics.environment_actions, **rollover},
                )
        before = environment.current
        fallback_before = metrics.fallback_actions
        try:
            if config.baseline_max_batch_actions == 1:
                actions = [agent.choose_action(before, history, journal, metrics)]
            else:
                actions = agent.choose_action_batch(before, history, journal, metrics)
        except SpendBudgetExceeded as exc:
            metrics.status = "spend_budget"
            journal.append(
                "spend_budget",
                {
                    "reason": str(exc),
                    "estimated_cost_usd": metrics.usage.estimated_cost_usd,
                    "max_spend_usd": config.max_spend_usd,
                },
            )
            return
        if config.baseline_max_batch_actions > 1:
            metrics.baseline_batches += 1
            metrics.baseline_actions_proposed += len(actions)
            journal.append(
                "baseline_batch_selected",
                {
                    "batch_index": metrics.baseline_batches,
                    "maximum_actions": config.baseline_max_batch_actions,
                    "actions": [{"id": action.id, "data": action.data} for action in actions],
                    "environment_actions_before": metrics.environment_actions,
                    "model_calls": metrics.model_calls,
                },
            )
        if (
            config.max_spend_usd > 0
            and (metrics.usage.estimated_cost_usd or 0.0) >= config.max_spend_usd
        ):
            metrics.status = "spend_budget"
            journal.append(
                "spend_budget",
                {
                    "reason": "API response reached spend cap before environment action",
                    "estimated_cost_usd": metrics.usage.estimated_cost_usd,
                    "max_spend_usd": config.max_spend_usd,
                },
            )
            return
        executed = 0
        stop_reason = "batch_complete"
        for action in actions:
            if environment.current.terminal:
                stop_reason = environment.current.state.lower()
                break
            if not _budget_ok(metrics, environment, config, started):
                stop_reason = (
                    metrics.status if metrics.status != "running" else "environment_action_budget"
                )
                break
            if action.id == 0 or action.id not in environment.current.available_actions:
                raise ValueError(
                    f"batched baseline action became illegal before execution: {action.id}"
                )
            kind = "fallback" if metrics.fallback_actions > fallback_before else "baseline"
            transition = _apply_action(environment, action, history, journal, metrics, kind=kind)
            executed += 1
            if transition.after.levels_completed > transition.before.levels_completed:
                stop_reason = "level_boundary"
                request_rollover = getattr(agent.client, "request_session_rollover", None)
                if callable(request_rollover):
                    request_rollover("level_boundary")
                break
            if transition.after.terminal:
                stop_reason = transition.after.state.lower()
                break
        if config.baseline_max_batch_actions > 1:
            if executed < len(actions):
                metrics.baseline_batches_truncated += 1
            journal.append(
                "baseline_batch_finished",
                {
                    "batch_index": metrics.baseline_batches,
                    "proposed_actions": len(actions),
                    "executed_actions": executed,
                    "stop_reason": stop_reason,
                    "environment_actions_after": metrics.environment_actions,
                    "levels_completed": environment.current.levels_completed,
                    "state": environment.current.state,
                },
            )


def _explore_once(
    agent: FsmHarnessAgent,
    environment: Environment,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
) -> bool:
    """FSM harness 的一次探索步；无候选则 fallback。成功执行返回 True。"""
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


def _run_fsm_harness(
    agent: FsmHarnessAgent,
    environment: Environment,
    config: ExperimentConfig,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    started: float,
) -> None:
    """声明式 FSM harness：强制探索 → 规划执行 → 预测不一致则 explore_burst。"""
    burst_remaining = 0
    while _budget_ok(metrics, environment, config, started):
        if _maybe_auto_reset(environment, config, history, journal, metrics):
            burst_remaining = max(config.explore_burst, 1)
            continue
        # 仍在初始探索配额内，或处于预测失败后的短 burst
        if metrics.exploration_actions < config.explore_steps or burst_remaining > 0:
            if not _explore_once(agent, environment, history, journal, metrics):
                metrics.status = "no_legal_action"
                return
            if burst_remaining > 0:
                burst_remaining -= 1
            continue

        # 剩余时间不足世界模型预算时，跳过规划，改探索/fallback
        remaining = config.run_timeout_seconds - (time.monotonic() - started)
        if remaining <= config.wm_time_reserve_seconds:
            journal.append(
                "wm_skipped",
                {
                    "reason": "insufficient_time_reserve",
                    "remaining_seconds": remaining,
                    "reserve_seconds": config.wm_time_reserve_seconds,
                },
            )
            if not _explore_once(agent, environment, history, journal, metrics):
                metrics.status = "timeout"
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
            # 未能规划：开一段探索 burst，再试
            burst_remaining = max(config.explore_burst - 1, 0)
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
            # for 正常走完（无 break）：继续外层 while，再规划
            continue

        # 规划中途 mismatch：再探索一段后重来
        if not matched_any or metrics.prediction_mismatches:
            burst_remaining = max(config.explore_burst - 1, 0)
            if _budget_ok(metrics, environment, config, started):
                _explore_once(agent, environment, history, journal, metrics)


def _prequential_predict(
    workspace: Workspace,
    runtime: ProgramRuntimeState,
    action: Action,
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    *,
    kind: str,
) -> ProgramPrediction | None:
    """Generate and log a prediction before the real environment action."""
    try:
        prediction = workspace.model().predict_runtime(runtime, action)
    except Exception as exc:
        metrics.prequential_predictions += 1
        metrics.prequential_mismatches += 1
        metrics.prediction_mismatches += 1
        mismatch = {
            "reason": f"prequential prediction error: {type(exc).__name__}: {exc}",
            "action_id": action.id,
            "kind": kind,
            "wm_version": workspace.version,
        }
        workspace.record_mismatch(mismatch)
        journal.append("prequential_prediction_error", mismatch)
        journal.append("prediction_mismatch", mismatch)
        return None
    metrics.prequential_predictions += 1
    journal.append(
        "prequential_prediction",
        {
            "kind": kind,
            "action": {"id": action.id, "data": action.data},
            "wm_version": workspace.version,
            "before_fingerprint": runtime.observation.fingerprint,
            "predicted_fingerprint": prediction.observation.fingerprint,
            "predicted_state": prediction.observation.state,
            "predicted_levels": prediction.observation.levels_completed,
            "events": list(prediction.events),
        },
    )
    return prediction


def _check_prequential_prediction(
    workspace: Workspace,
    prediction: ProgramPrediction,
    actual: Transition,
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    *,
    step_index: int,
    kind: str,
    allow_approximate: bool = False,
) -> bool:
    match = prediction_match_quality(
        prediction,
        actual.after,
        allow_approximate=allow_approximate,
    )
    if match.matched:
        metrics.prequential_matches += 1
        payload = {
            "action_id": actual.action.id,
            "step_index": step_index,
            "kind": kind,
            "events": list(prediction.events),
            "prequential": True,
            "exact": match.exact,
            "reason": match.reason,
            "differing_cells": match.differing_cells,
            "total_cells": match.total_cells,
        }
        if match.exact:
            journal.append("prediction_matched", payload)
            workspace.last_mismatch = None
        else:
            metrics.prequential_approximate_matches += 1
            workspace.record_soft_mismatch(payload)
            journal.append("prediction_approximate_match", payload)
        return True
    metrics.prequential_mismatches += 1
    metrics.prediction_mismatches += 1
    predicted, observed = prediction_mismatch_summary(prediction, actual.after)
    mismatch = {
        "reason": "prequential prediction differs from real observation",
        "action_id": actual.action.id,
        "step_index": step_index,
        "kind": kind,
        "wm_version": workspace.version,
        "predicted": predicted,
        "actual": observed,
    }
    workspace.record_mismatch(mismatch)
    journal.append("prediction_mismatch", mismatch)
    return False


def _schema_explore_step(
    environment: Environment,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    *,
    reason: str,
    workspace: Workspace | None = None,
) -> bool:
    """强制执行一步探索（或 fallback）；成功返回 True。"""
    # Do not explore while dead/won — caller should auto-reset instead.
    if environment.current.state in {"GAME_OVER", "WIN", "NOT_PLAYED"}:
        journal.append(
            "explore_skipped_terminal",
            {"reason": reason, "state": environment.current.state},
        )
        return False
    action = next_explore_action(environment.current, history)
    kind = "exploration"
    if action is None:
        action = choose_fallback_action(environment.current, history)
        if action is None:
            return False
        metrics.fallback_actions += 1
        kind = "fallback"
        journal.append(
            "fallback_action",
            {
                "reason": reason,
                "action": {"id": action.id, "data": action.data},
            },
        )
    else:
        journal.append(
            "forced_explore",
            {
                "reason": reason,
                "action": {"id": action.id, "data": action.data},
            },
        )
    prediction: ProgramPrediction | None = None
    if workspace is not None and workspace.certified:
        try:
            runtime = workspace.model().runtime_from_history(environment.current, history)
        except Exception as exc:
            runtime = None
            mismatch = {
                "reason": f"cannot reconstruct prequential runtime: {type(exc).__name__}: {exc}",
                "action_id": action.id,
                "kind": "exploration",
                "wm_version": workspace.version,
            }
            metrics.prequential_predictions += 1
            metrics.prequential_mismatches += 1
            metrics.prediction_mismatches += 1
            workspace.record_mismatch(mismatch)
            journal.append("prediction_mismatch", mismatch)
        if runtime is not None:
            prediction = _prequential_predict(
                workspace,
                runtime,
                action,
                journal,
                metrics,
                kind="exploration",
            )
    transition = _apply_action(
        environment,
        action,
        history,
        journal,
        metrics,
        kind="exploration",
    )
    if workspace is not None and prediction is not None:
        _check_prequential_prediction(
            workspace,
            prediction,
            transition,
            journal,
            metrics,
            step_index=0,
            kind="exploration",
        )
    del kind
    return True


def _deliberation_turn_budget(
    config: ExperimentConfig,
    metrics: RunMetrics,
    workspace: Workspace,
) -> tuple[int, list[str]]:
    """Allocate more theory turns to surprises and fewer to routine states.

    This keeps the model-call budget spread across the environment horizon while
    preserving enough turns to revise/resolve after genuinely informative events.
    """
    remaining_calls = max(config.max_model_calls_per_run - metrics.model_calls, 0)
    remaining_actions = max(
        config.max_environment_actions - metrics.environment_actions,
        1,
    )
    triggers: list[str] = []
    if workspace.mismatch_blocks_planning:
        triggers.append("prediction_mismatch")
    elif workspace.last_mismatch is not None and workspace.last_mismatch.get("severity") == "soft":
        triggers.append("approximate_prediction")
    if workspace.unresolved_observed_experiments():
        triggers.append("experiment_outcome")
    if not workspace.certified:
        triggers.append("uncertified_model")
    if config.agent_runtime == "codex_cli":
        # A coding-agent turn can inspect/edit/test multiple files. Allocate a
        # whole episode. Compound schema_cycle normally closes in one turn; a
        # triggered mismatch gets one repair turn rather than 8-12 full agents.
        target = 2 if triggers else 1
        budget = min(config.deliberation_max_turns, remaining_calls, target)
        return max(budget, 0), triggers or ["routine"]
    fair_share = max(1, remaining_calls // remaining_actions)
    if "prediction_mismatch" in triggers:
        target = 6
    elif "uncertified_model" in triggers:
        target = 5
    else:
        target = 4
    target = max(target, min(fair_share, 6))
    budget = min(config.deliberation_max_turns, remaining_calls, target)
    return max(budget, 0), triggers or ["routine"]


def _run_schema_harness(
    agent: SchemaHarnessAgent,
    environment: Environment,
    config: ExperimentConfig,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    started: float,
    workspace: Workspace,
) -> None:
    """程序世界模型 harness：外环调 deliberation，执行 commit，核对 planned 预测。"""
    idle_theory_rounds = 0
    while _budget_ok(metrics, environment, config, started):
        if _maybe_auto_reset(environment, config, history, journal, metrics, workspace=workspace):
            idle_theory_rounds = 0
            continue
        if (
            config.max_spend_usd > 0
            and (metrics.usage.estimated_cost_usd or 0.0) >= config.max_spend_usd
        ):
            metrics.status = "spend_budget"
            journal.append(
                "spend_budget",
                {
                    "estimated_cost_usd": metrics.usage.estimated_cost_usd,
                    "max_spend_usd": config.max_spend_usd,
                },
            )
            return
        remaining = config.run_timeout_seconds - (time.monotonic() - started)
        if remaining <= config.wm_time_reserve_seconds:
            # 时间不够做内环：fallback 探索一步
            journal.append(
                "wm_skipped",
                {
                    "reason": "insufficient_time_reserve",
                    "remaining_seconds": remaining,
                    "reserve_seconds": config.wm_time_reserve_seconds,
                },
            )
            if config.schema_commit_only:
                metrics.status = "timeout"
                return
            if not _schema_explore_step(
                environment,
                history,
                journal,
                metrics,
                reason="insufficient_time_reserve",
                workspace=workspace,
            ):
                if environment.current.state == "GAME_OVER":
                    continue
                metrics.status = "timeout"
                return
            continue

        # Cold-start explore quota: gather Timeline evidence before long theorizing.
        if not config.schema_commit_only and metrics.environment_actions < config.explore_steps:
            if not _schema_explore_step(
                environment,
                history,
                journal,
                metrics,
                reason=f"cold_start_explore<{config.explore_steps}",
                workspace=workspace,
            ):
                if environment.current.state == "GAME_OVER":
                    continue
                metrics.status = "no_legal_action"
                return
            continue

        # After several theory-only rounds, force an explore burst.
        if not config.schema_commit_only and idle_theory_rounds >= max(config.explore_burst, 1):
            burst = max(config.explore_burst, 1)
            journal.append(
                "forced_explore_burst",
                {"reason": "idle_theory_rounds", "burst": burst, "idle": idle_theory_rounds},
            )
            for _ in range(burst):
                if not _budget_ok(metrics, environment, config, started):
                    return
                # Mid-burst GAME_OVER: stop exploring and let the outer loop RESET.
                if environment.current.state == "GAME_OVER":
                    break
                if environment.current.state == "WIN":
                    return
                if not _schema_explore_step(
                    environment,
                    history,
                    journal,
                    metrics,
                    reason="idle_theory_explore_burst",
                    workspace=workspace,
                ):
                    if environment.current.state == "GAME_OVER":
                        break
                    metrics.status = "no_legal_action"
                    return
            idle_theory_rounds = 0
            continue

        turn_budget, deliberation_triggers = _deliberation_turn_budget(
            config,
            metrics,
            workspace,
        )
        if turn_budget <= 0:
            metrics.status = "model_call_budget"
            metrics.model_budget_exhausted_at_action = metrics.environment_actions
            journal.append(
                "model_call_budget",
                {
                    "model_calls": metrics.model_calls,
                    "max_model_calls": config.max_model_calls_per_run,
                    "environment_actions": metrics.environment_actions,
                },
            )
            return
        metrics.event_driven_deliberations += 1
        journal.append(
            "deliberation_scheduled",
            {
                "env_step": metrics.environment_actions,
                "turn_budget": turn_budget,
                "triggers": deliberation_triggers,
                "remaining_model_calls": (config.max_model_calls_per_run - metrics.model_calls),
                "remaining_environment_actions": (
                    config.max_environment_actions - metrics.environment_actions
                ),
            },
        )
        session = DeliberationSession(
            agent.client,
            workspace,
            max_turns=turn_budget,
            planner_max_nodes=config.planner_max_nodes,
            max_plan_steps=config.max_plan_steps,
            max_model_calls=config.max_model_calls_per_run,
            max_spend_usd=config.max_spend_usd,
            spend_reserve_usd=config.request_spend_reserve_usd,
            vision_enabled=config.model.vision_enabled,
            env_actions_so_far=metrics.environment_actions,
            allow_approximate_visual_matches=(config.allow_approximate_visual_matches),
            max_total_tokens=config.max_total_tokens_per_run,
            max_uncached_tokens=config.max_uncached_tokens_per_run,
            max_output_tokens=config.max_output_tokens_per_run,
            token_reserve_per_call=config.token_reserve_per_call,
            max_notional_cost_usd=config.max_notional_cost_usd,
        )
        result = session.run(environment.current, history, journal, metrics)
        journal.append(
            "deliberation_finished",
            {
                "reason": result.reason,
                "has_commit": result.commit is not None,
                "tools": [item.get("tool") for item in result.tool_trace],
                "env_step": metrics.environment_actions,
            },
        )
        if result.commit is None:
            if result.reason == "infrastructure_error":
                metrics.status = "infrastructure_error"
                metrics.error = "Codex transport failed before a model response"
                journal.append(
                    "infrastructure_error",
                    {
                        "reason": result.reason,
                        "model_calls": metrics.model_calls,
                        "environment_actions": metrics.environment_actions,
                        "transport_reconnects": metrics.codex_transport_reconnects,
                        "https_fallbacks": metrics.codex_https_fallbacks,
                        "transport_timeouts": metrics.codex_transport_timeouts,
                        "turn_failures": metrics.codex_turn_failures,
                    },
                )
                return
            if (
                result.reason == "model_call_budget"
                or metrics.model_calls >= config.max_model_calls_per_run
            ):
                metrics.status = "model_call_budget"
                metrics.model_budget_exhausted_at_action = metrics.environment_actions
                journal.append(
                    "model_call_budget",
                    {
                        "reason": result.reason,
                        "model_calls": metrics.model_calls,
                        "max_model_calls": config.max_model_calls_per_run,
                        "environment_actions": metrics.environment_actions,
                    },
                )
                return
            if result.reason == "spend_budget":
                metrics.status = "spend_budget"
                journal.append(
                    "spend_budget",
                    {
                        "reason": "deliberation request reserve reached",
                        "estimated_cost_usd": metrics.usage.estimated_cost_usd,
                        "max_spend_usd": config.max_spend_usd,
                        "request_spend_reserve_usd": config.request_spend_reserve_usd,
                    },
                )
                return
            if result.reason in {
                "token_budget",
                "uncached_token_budget",
                "output_token_budget",
                "notional_cost_budget",
            }:
                metrics.status = result.reason
                journal.append(
                    result.reason,
                    {
                        "total_tokens": metrics.usage.total_tokens,
                        "max_total_tokens": config.max_total_tokens_per_run,
                        "uncached_prompt_tokens": (metrics.usage.uncached_prompt_tokens),
                        "max_uncached_tokens": config.max_uncached_tokens_per_run,
                        "output_tokens": metrics.usage.completion_tokens,
                        "max_output_tokens": config.max_output_tokens_per_run,
                        "notional_cost_usd": metrics.usage.notional_cost_usd,
                        "max_notional_cost_usd": config.max_notional_cost_usd,
                    },
                )
                return
            idle_theory_rounds += 1
            # 内环无提交：fallback 一步，避免空转卡死
            if config.schema_commit_only:
                journal.append(
                    "commit_only_rescheduled",
                    {
                        "reason": result.reason,
                        "idle_theory_rounds": idle_theory_rounds,
                    },
                )
                continue
            if not _schema_explore_step(
                environment,
                history,
                journal,
                metrics,
                reason=f"no commit: {result.reason}",
                workspace=workspace,
            ):
                if environment.current.state == "GAME_OVER":
                    continue
                metrics.status = result.reason or "no_commit"
                return
            continue

        commit = result.commit
        model = workspace.model() if workspace.certified else None
        runtime: ProgramRuntimeState | None = None
        if model is not None:
            try:
                runtime = model.runtime_from_history(environment.current, history)
            except Exception as exc:
                mismatch = {
                    "reason": f"cannot reconstruct plan runtime: {type(exc).__name__}: {exc}",
                    "kind": commit.kind,
                    "plan_id": commit.plan_id,
                    "wm_version": workspace.version,
                }
                metrics.prediction_mismatches += 1
                metrics.prequential_predictions += 1
                metrics.prequential_mismatches += 1
                workspace.record_mismatch(mismatch)
                journal.append("prediction_mismatch", mismatch)
                if commit.kind in {"planned", "navigation"}:
                    idle_theory_rounds += 1
                    continue
        journal.append(
            "commit_execution_started",
            {
                "kind": commit.kind,
                "plan_id": commit.plan_id,
                "experiment_id": commit.experiment_id,
                "actions": [{"id": action.id, "data": action.data} for action in commit.actions],
                "rationale": commit.rationale,
                "evidence_seq": list(commit.evidence_seq),
                "wm_version": workspace.version,
                "current_fingerprint": environment.current.fingerprint,
            },
        )
        acted = False
        for index, action in enumerate(commit.actions):
            if not _budget_ok(metrics, environment, config, started):
                return
            if action.id not in environment.current.available_actions:
                metrics.prediction_mismatches += 1
                mismatch = {
                    "reason": "committed action no longer legal",
                    "action_id": action.id,
                }
                workspace.record_mismatch(mismatch)
                journal.append("prediction_mismatch", mismatch)
                break
            before = environment.current
            prediction: ProgramPrediction | None = None
            if model is not None and runtime is not None:
                prediction = _prequential_predict(
                    workspace,
                    runtime,
                    action,
                    journal,
                    metrics,
                    kind=commit.kind,
                )
                if prediction is None and commit.kind in {"planned", "navigation"}:
                    idle_theory_rounds += 1
                    break
            transition = _apply_action(
                environment,
                action,
                history,
                journal,
                metrics,
                kind=commit.kind,
            )
            if commit.experiment_id is not None:
                outcome = {
                    "action": {
                        "id": transition.action.id,
                        "data": transition.action.data,
                    },
                    "before_fingerprint": transition.before.fingerprint,
                    "after_fingerprint": transition.after.fingerprint,
                    "delta": transition.delta().to_dict(),
                    "levels_before": transition.before.levels_completed,
                    "levels_after": transition.after.levels_completed,
                    "state_after": transition.after.state,
                }
                observed_record = journal.append(
                    "experiment_observed",
                    {
                        "env_step": metrics.environment_actions,
                        "experiment_id": commit.experiment_id,
                        **outcome,
                    },
                )
                hypothesis_version = workspace.record_experiment_outcome(
                    commit.experiment_id,
                    outcome,
                    evidence_seq=int(observed_record["sequence"]),
                )
                metrics.experiments_observed += 1
                journal.append(
                    "hypothesis_ledger_revision",
                    {
                        "env_step": metrics.environment_actions,
                        "hypothesis_version": hypothesis_version,
                        "experiment_id": commit.experiment_id,
                        "reason": "experiment_observed",
                        "path": str(workspace.hypothesis_ledger_path),
                    },
                )
            if commit.kind == "planned":
                metrics.bfs_derived_planned_actions += 1
            acted = True
            idle_theory_rounds = 0
            level_advanced = transition.after.levels_completed > before.levels_completed
            prediction_matched = True
            if prediction is not None:
                prediction_matched = _check_prequential_prediction(
                    workspace,
                    prediction,
                    transition,
                    journal,
                    metrics,
                    step_index=index,
                    kind=commit.kind,
                    allow_approximate=config.allow_approximate_visual_matches,
                )
                if prediction_matched:
                    runtime = model.accept_actual(prediction, transition.after)
            if level_advanced:
                boundary = {
                    "reason": "level_boundary_requires_recertification",
                    "action_id": action.id,
                    "kind": commit.kind,
                    "plan_id": commit.plan_id,
                    "levels_before": before.levels_completed,
                    "levels_after": transition.after.levels_completed,
                }
                workspace.record_boundary(boundary, reason="level_boundary")
                journal.append("level_boundary", boundary)
                request_rollover = getattr(agent.client, "request_session_rollover", None)
                if callable(request_rollover):
                    request_rollover("level_boundary")
                break
            if not prediction_matched:
                idle_theory_rounds += 1
                break
            if transition.after.state in {"GAME_OVER", "WIN"}:
                break
        if not acted:
            idle_theory_rounds += 1


def _write_trace_index(
    journal_path: Path,
    workspace: Workspace,
    metrics: RunMetrics,
) -> None:
    """Write a short human index for post-run sampling of thinking / notes / WM."""
    records = list(AppendOnlyJournal.read_records(journal_path))
    categories: dict[str, list[str]] = {
        "Level progress and boundaries": [],
        "Hypotheses and WM revisions": [],
        "Backtests and BFS plans": [],
        "Prequential predictions": [],
        "Commits and experiments": [],
        "Resets, mismatches, and spend stops": [],
        "Returned reasoning text": [],
    }
    for record in records:
        event = record.get("event")
        payload = record.get("payload") or {}
        seq = record.get("sequence")
        if event == "notes_revision":
            categories["Hypotheses and WM revisions"].append(
                f"- seq={seq} notes_revision v{payload.get('notes_version')} "
                f"env_step={payload.get('env_step')} preview={payload.get('text_preview', '')[:80]!r}"
            )
        elif event == "wm_revision":
            categories["Hypotheses and WM revisions"].append(
                f"- seq={seq} wm_revision v{payload.get('version')} "
                f"kind={payload.get('kind')} path={payload.get('path')}"
            )
        elif event in {"hypothesis_revision", "hypothesis_ledger_revision"}:
            categories["Hypotheses and WM revisions"].append(
                f"- seq={seq} {event} "
                f"v{payload.get('version', payload.get('hypothesis_version'))} "
                f"updated={payload.get('updated_ids')} "
                f"experiment_id={payload.get('experiment_id')}"
            )
        elif event == "transition":
            before = payload.get("before") or {}
            after = payload.get("after") or {}
            if int(after.get("levels_completed", 0)) > int(before.get("levels_completed", 0)):
                categories["Level progress and boundaries"].append(
                    f"- seq={seq} level_up "
                    f"{before.get('levels_completed')}→{after.get('levels_completed')} "
                    f"action_id={(payload.get('action') or {}).get('id')}"
                )
        elif event == "level_boundary":
            categories["Level progress and boundaries"].append(
                f"- seq={seq} level_boundary "
                f"{payload.get('levels_before')}→{payload.get('levels_after')} "
                f"plan_id={payload.get('plan_id')}"
            )
        elif event == "level_resource_checkpoint":
            categories["Level progress and boundaries"].append(
                f"- seq={seq} level_resource_checkpoint "
                f"level={payload.get('level')} "
                f"actions={payload.get('environment_actions')} "
                f"model_calls={payload.get('model_calls')} "
                f"total_tokens={payload.get('total_tokens')}"
            )
        elif event == "prediction_mismatch":
            categories["Resets, mismatches, and spend stops"].append(
                f"- seq={seq} prediction_mismatch reason={payload.get('reason')} "
                f"action_id={payload.get('action_id')}"
            )
        elif event == "life_reset":
            categories["Resets, mismatches, and spend stops"].append(
                f"- seq={seq} life_reset #{payload.get('reset_index')} "
                f"levels={payload.get('levels_completed_after')}"
            )
        elif event == "spend_budget":
            categories["Resets, mismatches, and spend stops"].append(
                f"- seq={seq} spend_budget cost={payload.get('estimated_cost_usd')} "
                f"cap={payload.get('max_spend_usd')}"
            )
        elif event == "model_call_budget":
            categories["Resets, mismatches, and spend stops"].append(
                f"- seq={seq} model_call_budget calls={payload.get('model_calls')} "
                f"env_step={payload.get('environment_actions')}"
            )
        elif event == "infrastructure_error":
            categories["Resets, mismatches, and spend stops"].append(
                f"- seq={seq} infrastructure_error calls={payload.get('model_calls')} "
                f"reconnects={payload.get('transport_reconnects')} "
                f"fallbacks={payload.get('https_fallbacks')} "
                f"timeouts={payload.get('transport_timeouts')}"
            )
        elif event == "bfs_plan_created":
            categories["Backtests and BFS plans"].append(
                f"- seq={seq} bfs_plan plan_id={payload.get('plan_id')} "
                f"wm=v{payload.get('wm_version')} actions={len(payload.get('actions') or [])}"
            )
        elif event == "deliberation_tool":
            args = payload.get("args") or {}
            result = payload.get("result") or {}
            if payload.get("tool") == "run_backtest":
                bt = result.get("result") or {}
                categories["Backtests and BFS plans"].append(
                    f"- seq={seq} backtest passed={bt.get('passed')} "
                    f"checked={bt.get('checked')} mismatch={bt.get('mismatch_index')}"
                )
            elif payload.get("tool") == "run_bfs" and not result.get("found"):
                categories["Backtests and BFS plans"].append(
                    f"- seq={seq} bfs_no_plan error={result.get('error')!r}"
                )
            elif payload.get("tool") == "commit_actions":
                categories["Commits and experiments"].append(
                    f"- seq={seq} commit kind={args.get('kind')} "
                    f"plan_id={result.get('plan_id')} "
                    f"experiment_id={result.get('experiment_id')} "
                    f"accepted={result.get('accepted')}"
                )
        elif event == "experiment_proposed":
            categories["Commits and experiments"].append(
                f"- seq={seq} experiment id={payload.get('experiment_id')} "
                f"action_id={(payload.get('action') or {}).get('id')} "
                f"hypotheses={len(payload.get('hypotheses') or [])}"
            )
        elif event == "experiment_observed":
            categories["Commits and experiments"].append(
                f"- seq={seq} experiment_observed id={payload.get('experiment_id')} "
                f"action_id={(payload.get('action') or {}).get('id')} "
                f"levels={payload.get('levels_before')}→{payload.get('levels_after')}"
            )
        elif event in {
            "prequential_prediction",
            "prediction_matched",
            "prediction_approximate_match",
        }:
            if event == "prequential_prediction" or payload.get("prequential"):
                categories["Prequential predictions"].append(
                    f"- seq={seq} {event} kind={payload.get('kind')} "
                    f"action_id={(payload.get('action') or {}).get('id', payload.get('action_id'))} "
                    f"events={payload.get('events')}"
                )
        elif event == "vision_frame":
            categories["Level progress and boundaries"].append(
                f"- seq={seq} vision_frame env_step={payload.get('env_step')} "
                f"sha256={str(payload.get('sha256', ''))[:12]} path={payload.get('path')}"
            )
        elif event == "model_response" and payload.get("reasoning_status") == "present":
            categories["Returned reasoning text"].append(
                f"- seq={seq} reasoning_text present turn={payload.get('turn')} "
                f"env_step={payload.get('env_step')}"
            )

    def _compact(items: list[str]) -> list[str]:
        if len(items) <= 10:
            return items
        return items[:3] + [f"- … {len(items) - 8} omitted …"] + items[-5:]

    reasoning_statuses = [
        (record.get("payload") or {}).get("reasoning_status")
        for record in records
        if record.get("event") == "model_response"
    ]
    notes_writes = sum(1 for record in records if record.get("event") == "notes_revision")
    wm_writes = sum(1 for record in records if record.get("event") == "wm_revision")
    tokens_only = sum(1 for status in reasoning_statuses if status == "tokens_only")
    present = sum(1 for status in reasoning_statuses if status == "present")

    lines = [
        "# Trace index (auto-generated)",
        "",
        f"- agent: `{metrics.agent}`",
        f"- status: `{metrics.status}`",
        f"- levels_completed: {metrics.levels_completed}",
        f"- environment_actions: {metrics.environment_actions}",
        f"- journal: `{journal_path}`",
        f"- workspace: `{workspace.root}`",
        f"- native Codex events: `{workspace.root / 'codex-cli-events.jsonl'}` "
        "(when ARC_AGENT_RUNTIME=codex_cli)",
        f"- notes.md: `{workspace.notes_path}` (notes_version={workspace.notes_version})",
        f"- hypotheses.json: `{workspace.hypothesis_ledger_path}` "
        f"(hypothesis_version={workspace.hypothesis_version})",
        f"- world_model.py: `{workspace.world_model_path}` (wm_version={workspace.version})",
        f"- wm_versions/: `{workspace.wm_versions_dir}`",
        f"- notes_history/: `{workspace.notes_history_dir}`",
        f"- hypothesis_versions/: `{workspace.hypothesis_versions_dir}`",
        f"- vision_frames/: `{workspace.vision_frames_dir}`",
        f"- notes_revision events: {notes_writes}",
        f"- wm_revision events: {wm_writes}",
        f"- reasoning_status present/tokens_only: {present}/{tokens_only}",
        f"- level_resource_checkpoints: {canonical_json(metrics.level_checkpoints)}",
        f"- BFS plans / BFS-derived planned actions: "
        f"{metrics.bfs_plans_generated}/{metrics.bfs_derived_planned_actions}",
        f"- navigation actions: {metrics.navigation_actions}",
        f"- BFS no-plan results/cache hits: "
        f"{metrics.bfs_no_plan_results}/{metrics.bfs_no_plan_cache_hits}",
        f"- prequential predictions/matches/mismatches: "
        f"{metrics.prequential_predictions}/{metrics.prequential_matches}/"
        f"{metrics.prequential_mismatches}",
        f"- prequential approximate matches: {metrics.prequential_approximate_matches}",
        f"- discriminating experiments: {metrics.discriminating_experiments}",
        f"- experiments observed/resolved: "
        f"{metrics.experiments_observed}/{metrics.experiments_resolved}",
        f"- event-driven deliberations: {metrics.event_driven_deliberations}",
        f"- max deliberation context chars: {metrics.max_deliberation_context_chars}",
        f"- Codex transport reconnects / HTTPS fallbacks / timeouts / turn failures: "
        f"{metrics.codex_transport_reconnects}/{metrics.codex_https_fallbacks}/"
        f"{metrics.codex_transport_timeouts}/{metrics.codex_turn_failures}",
        f"- Codex recovered post-completion process hangs: "
        f"{metrics.codex_post_completion_forced_exits}",
        f"- model budget exhausted at action: {metrics.model_budget_exhausted_at_action}",
        "",
    ]
    for title, items in categories.items():
        lines.extend([f"## {title}", ""])
        lines.extend(_compact(items) or ["- (none)"])
        lines.append("")
    lines.extend(
        [
            "## How to spot-check",
            "",
            "1. Open `hypotheses.json` and `hypothesis_versions/` for stable theory status/evidence.",
            "2. Open `notes.md` and `notes_history/` for the readable synthesis.",
            "3. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.",
            '4. In the jsonl, search `"event":"deliberation_turn"` or `"event":"model_response"`.',
            "5. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.",
            "",
        ]
    )
    (workspace.root / "trace_index.md").write_text("\n".join(lines), encoding="utf-8")
