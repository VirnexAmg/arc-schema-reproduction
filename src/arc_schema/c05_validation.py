from __future__ import annotations

"""Paid-gated ToyEnvironment acceptance test for the complete Codex Schema loop."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from arc_schema.agents import SchemaHarnessAgent
from arc_schema.config import ExperimentConfig
from arc_schema.history import AppendOnlyJournal
from arc_schema.mock import ToyEnvironment
from arc_schema.runner import run_agent


def c05_config(base: ExperimentConfig, root: Path) -> ExperimentConfig:
    """Make C0.5 independent of the ARC environment and formal C1 budgets."""
    return replace(
        base,
        agent_runtime="codex_cli",
        game_id="toy",
        runs=1,
        output_dir=root,
        max_environment_actions=4,
        max_model_calls_per_run=min(max(base.max_model_calls_per_run, 1), 4),
        deliberation_max_turns=2,
        max_plan_steps=4,
        planner_max_nodes=100,
        explore_steps=0,
        explore_burst=1,
        wm_time_reserve_seconds=0.0,
        run_timeout_seconds=min(max(base.run_timeout_seconds, 60.0), 3600.0),
        schema_commit_only=True,
        allow_approximate_visual_matches=False,
        target_levels_completed=1,
        max_total_tokens_per_run=(
            min(base.max_total_tokens_per_run, 3_000_000)
            if base.max_total_tokens_per_run > 0
            else 3_000_000
        ),
        max_uncached_tokens_per_run=(
            min(base.max_uncached_tokens_per_run, 500_000)
            if base.max_uncached_tokens_per_run > 0
            else 500_000
        ),
        max_output_tokens_per_run=(
            min(base.max_output_tokens_per_run, 100_000)
            if base.max_output_tokens_per_run > 0
            else 100_000
        ),
        token_reserve_per_call=max(base.token_reserve_per_call, 400_000),
        max_notional_cost_usd=(
            min(base.max_notional_cost_usd, 5.0) if base.max_notional_cost_usd > 0 else 5.0
        ),
        codex_max_turns_per_thread=4,
        codex_compound_cycle=True,
        max_spend_usd=0.0,
        experiment_max_spend_usd=0.0,
        auto_reset_on_game_over=False,
    )


def run_c05(
    base: ExperimentConfig,
    root: Path,
    client: Any,
    *,
    require_codex_trace: bool = True,
) -> dict[str, Any]:
    """Run the toy closed loop and write a machine-readable acceptance report."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    config = c05_config(base, root)
    journal_path = root / "c05-run.jsonl"
    metrics = run_agent(
        SchemaHarnessAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=journal_path,
    )
    workspace = root / "workspace-harness-0"
    records = list(AppendOnlyJournal.read_records(journal_path))
    backtests: list[dict[str, Any]] = []
    for record in records:
        if record.get("event") != "deliberation_tool":
            continue
        payload = record.get("payload") or {}
        result = payload.get("result") or {}
        if payload.get("tool") == "run_backtest":
            backtests.append(result)
        elif payload.get("tool") == "schema_cycle" and isinstance(result, dict):
            nested = result.get("backtest")
            if isinstance(nested, dict):
                backtests.append(nested)
    checked = max(
        [
            int((item.get("result") or {}).get("checked", 0))
            for item in backtests
            if isinstance(item, dict)
        ],
        default=0,
    )
    exact_certified = any(bool(item.get("certified_exact")) for item in backtests)
    events = [str(record.get("event")) for record in records]
    codex_trace = workspace / "codex-cli-events.jsonl"
    checks = {
        "completed_toy_level": metrics.levels_completed >= 1,
        "within_four_model_calls": 0 < metrics.model_calls <= 4,
        "within_configured_model_call_cap": (
            0 < metrics.model_calls <= config.max_model_calls_per_run
        ),
        "world_model_revised": "wm_revision" in events,
        "notes_revised": "notes_revision" in events,
        "non_vacuous_backtest": checked > 0,
        "exact_certification": exact_certified,
        "bfs_plan_created": "bfs_plan_created" in events,
        "planned_commit_executed": any(
            record.get("event") == "commit_execution_started"
            and (record.get("payload") or {}).get("kind") == "planned"
            for record in records
        ),
        "prequential_match": metrics.prequential_matches > 0,
        "trace_index_written": (workspace / "trace_index.md").exists(),
        "codex_jsonl_written": (codex_trace.exists() and codex_trace.stat().st_size > 0)
        if require_codex_trace
        else True,
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "purpose": "C0.5 toy full-loop acceptance; no ARC environment used",
        "root": str(root),
        "journal": str(journal_path),
        "workspace": str(workspace),
        "checks": checks,
        "metrics": metrics.to_dict(),
        "backtest_checked_max": checked,
        "thread_prefix": (str(getattr(client, "thread_id", ""))[:8] or None),
    }
    (root / "c05-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report
