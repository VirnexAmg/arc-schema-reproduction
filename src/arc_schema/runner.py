from __future__ import annotations

"""
实验外环：驱动 agent 与真实环境交互，记录 journal / metrics。

本模块是 harness 的「执行壳」，按 agent 类型分派三条路径：
1. BaselineAgent：每步直接选动作并执行；
2. FsmHarnessAgent：先探索，再声明式世界模型规划，预测不一致则短 burst 再探索；
3. SchemaHarnessAgent：创建 Workspace，跑 DeliberationSession 内环，仅执行 commit 的动作，
   并对 planned 步骤做 ensure_model_predictions 核对。

公共约定：
- _budget_ok 统一检查终局 / 环境动作上限 / 墙钟超时；
- _apply_action 执行一步、记账、写 Timeline 与 journal；
- run_agent 负责启动/收尾（scorecard、wall_clock、run_finished），异常记为 failed。
"""

import time
from pathlib import Path

from arc_schema.agents import (
    BaselineAgent,
    FsmHarnessAgent,
    SchemaHarnessAgent,
    choose_fallback_action,
)
from arc_schema.config import ExperimentConfig
from arc_schema.context import next_explore_action
from arc_schema.core import Action, RunMetrics, Transition, canonical_json
from arc_schema.deliberation import DeliberationSession, ensure_model_predictions
from arc_schema.environment import Environment
from arc_schema.history import AppendOnlyJournal
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
        workspace.certified = False
        workspace.last_backtest = None
        workspace.mismatch_blocks_planning = True
        workspace.last_mismatch = {
            "reason": "life_reset_after_game_over",
            "reset_index": metrics.game_over_resets,
            "message": (
                "Episode died. Prior transitions remain in the Timeline. "
                "Revise step()/is_goal if needed, then run_backtest on the FULL history "
                "before planning again."
            ),
        }
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
    """基线循环：每步由 agent 选动作并执行，直至预算耗尽。"""
    while _budget_ok(metrics, environment, config, started):
        if _maybe_auto_reset(environment, config, history, journal, metrics):
            continue
        before = environment.current
        fallback_before = metrics.fallback_actions
        action = agent.choose_action(before, history, journal, metrics)
        kind = "fallback" if metrics.fallback_actions > fallback_before else "baseline"
        _apply_action(environment, action, history, journal, metrics, kind=kind)


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
        if remaining < config.wm_time_reserve_seconds:
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


def _schema_explore_step(
    environment: Environment,
    history: list[Transition],
    journal: AppendOnlyJournal,
    metrics: RunMetrics,
    *,
    reason: str,
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
    _apply_action(environment, action, history, journal, metrics, kind="exploration")
    del kind
    return True


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
        if _maybe_auto_reset(
            environment, config, history, journal, metrics, workspace=workspace
        ):
            idle_theory_rounds = 0
            continue
        if config.max_spend_usd > 0 and (metrics.usage.estimated_cost_usd or 0.0) >= config.max_spend_usd:
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
        if remaining < config.wm_time_reserve_seconds:
            # 时间不够做内环：fallback 探索一步
            journal.append(
                "wm_skipped",
                {
                    "reason": "insufficient_time_reserve",
                    "remaining_seconds": remaining,
                    "reserve_seconds": config.wm_time_reserve_seconds,
                },
            )
            if not _schema_explore_step(
                environment, history, journal, metrics, reason="insufficient_time_reserve"
            ):
                if environment.current.state == "GAME_OVER":
                    continue
                metrics.status = "timeout"
                return
            continue

        # Cold-start explore quota: gather Timeline evidence before long theorizing.
        if metrics.environment_actions < config.explore_steps:
            if not _schema_explore_step(
                environment,
                history,
                journal,
                metrics,
                reason=f"cold_start_explore<{config.explore_steps}",
            ):
                if environment.current.state == "GAME_OVER":
                    continue
                metrics.status = "no_legal_action"
                return
            continue

        # After several theory-only rounds, force an explore burst.
        if idle_theory_rounds >= max(config.explore_burst, 1):
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
                ):
                    if environment.current.state == "GAME_OVER":
                        break
                    metrics.status = "no_legal_action"
                    return
            idle_theory_rounds = 0
            continue

        session = DeliberationSession(
            agent.client,
            workspace,
            max_turns=config.deliberation_max_turns,
            planner_max_nodes=config.planner_max_nodes,
            max_plan_steps=config.max_plan_steps,
            max_model_calls=config.max_model_calls_per_run,
            max_spend_usd=config.max_spend_usd,
            vision_enabled=config.model.vision_enabled,
            env_actions_so_far=metrics.environment_actions,
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
            idle_theory_rounds += 1
            # 内环无提交：fallback 一步，避免空转卡死
            if not _schema_explore_step(
                environment,
                history,
                journal,
                metrics,
                reason=f"no commit: {result.reason}",
            ):
                if environment.current.state == "GAME_OVER":
                    continue
                metrics.status = result.reason or "no_commit"
                return
            continue

        commit = result.commit
        model = workspace.model() if workspace.certified else None
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
            transition = _apply_action(
                environment,
                action,
                history,
                journal,
                metrics,
                kind=commit.kind if commit.kind == "planned" else "exploration",
            )
            acted = True
            idle_theory_rounds = 0
            if transition.after.state in {"GAME_OVER", "WIN"}:
                break
            # planned 且模型仍认证：逐步核对预测；失败则记 mismatch 并中断本批 commit
            if commit.kind == "planned" and model is not None:
                if not ensure_model_predictions(model, before, action, transition.after):
                    metrics.prediction_mismatches += 1
                    mismatch = {
                        "reason": "predicted state differs from real observation",
                        "action_id": action.id,
                        "step_index": index,
                        "delta": transition.delta().to_dict(),
                        "predicted_levels": None,
                        "actual_levels": transition.after.levels_completed,
                    }
                    try:
                        predicted = model.predict(before, action)
                        mismatch["predicted_levels"] = predicted.levels_completed
                        mismatch["predicted_state"] = predicted.state
                        mismatch["actual_state"] = transition.after.state
                    except Exception as exc:
                        mismatch["predict_error"] = f"{type(exc).__name__}: {exc}"
                    workspace.record_mismatch(mismatch)
                    journal.append("prediction_mismatch", mismatch)
                    idle_theory_rounds += 1
                    break
                journal.append("prediction_matched", {"action_id": action.id, "step_index": index})
                workspace.last_mismatch = None
        if not acted:
            idle_theory_rounds += 1


def _write_trace_index(
    journal_path: Path,
    workspace: Workspace,
    metrics: RunMetrics,
) -> None:
    """Write a short human index for post-run sampling of thinking / notes / WM."""
    records = list(AppendOnlyJournal.read_records(journal_path))
    highlights: list[str] = []
    for record in records:
        event = record.get("event")
        payload = record.get("payload") or {}
        seq = record.get("sequence")
        if event == "notes_revision":
            highlights.append(
                f"- seq={seq} notes_revision v{payload.get('notes_version')} "
                f"env_step={payload.get('env_step')} preview={payload.get('text_preview', '')[:80]!r}"
            )
        elif event == "wm_revision":
            highlights.append(
                f"- seq={seq} wm_revision v{payload.get('version')} "
                f"kind={payload.get('kind')} path={payload.get('path')}"
            )
        elif event == "prediction_mismatch":
            highlights.append(
                f"- seq={seq} prediction_mismatch reason={payload.get('reason')} "
                f"action_id={payload.get('action_id')}"
            )
        elif event == "deliberation_started":
            highlights.append(
                f"- seq={seq} deliberation_started env_step={payload.get('env_step')} "
                f"vision={payload.get('vision_enabled')} certified={payload.get('certified')}"
            )
        elif event == "life_reset":
            highlights.append(
                f"- seq={seq} life_reset #{payload.get('reset_index')} "
                f"levels={payload.get('levels_completed_after')}"
            )
        elif event == "model_response" and payload.get("reasoning_status") == "present":
            highlights.append(
                f"- seq={seq} reasoning_text present turn={payload.get('turn')} "
                f"env_step={payload.get('env_step')}"
            )

    # Keep a compact sample of up to ~12 highlights, preferring late mismatches / notes.
    if len(highlights) > 12:
        highlights = highlights[:4] + highlights[-8:]

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
        f"- notes.md: `{workspace.notes_path}` (notes_version={workspace.notes_version})",
        f"- world_model.py: `{workspace.world_model_path}` (wm_version={workspace.version})",
        f"- wm_versions/: `{workspace.wm_versions_dir}`",
        f"- notes_history/: `{workspace.notes_history_dir}`",
        f"- notes_revision events: {notes_writes}",
        f"- wm_revision events: {wm_writes}",
        f"- reasoning_status present/tokens_only: {present}/{tokens_only}",
        "",
        "## Sample jump points",
        "",
    ]
    lines.extend(highlights or ["- (no highlight events yet)"])
    lines.extend(
        [
            "",
            "## How to spot-check",
            "",
            "1. Open `notes.md` and `notes_history/` for hypothesis text.",
            "2. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.",
            "3. In the jsonl, search `\"event\":\"deliberation_turn\"` or `\"event\":\"model_response\"`.",
            "4. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.",
            "",
        ]
    )
    (workspace.root / "trace_index.md").write_text("\n".join(lines), encoding="utf-8")

