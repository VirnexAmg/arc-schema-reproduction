from __future__ import annotations

"""
实验编排与汇总：跑 baseline/harness、写 experiment.json、判断配对有效性。

阅读导引：
- run_experiment：按 config 循环 seed/run，调用 run_agent，落盘结果
- pair_validity：基础设施/超时等是否使 A/B 配对无效
- aggregate：跨 run 均值与标准差
注意：分两次单独跑的对照可能各自 paired_valid=null，可比性靠预注册与配置审计。
"""

import json
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arc_schema.agents import BaselineAgent, make_harness_agent
from arc_schema.config import ExperimentConfig
from arc_schema.core import RunMetrics
from arc_schema.deepseek_client import ModelClient
from arc_schema.environment import Environment
from arc_schema.history import AppendOnlyJournal
from arc_schema.runner import run_agent


EnvironmentFactory = Callable[[int], Environment]
ClientFactory = Callable[[], ModelClient]

VALID_SUCCESS_TERMINAL = {"win", "game_over", "target_levels_reached"}
VALID_BUDGET_TERMINAL = {
    "action_budget_exhausted",
    "model_call_budget",
    "token_budget",
    "uncached_token_budget",
    "output_token_budget",
    "notional_cost_budget",
}
VALID_SPEND_TERMINAL = {"spend_budget"}


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def _mean_stdev(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values) if values else 0.0,
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def pair_validity(
    baseline: dict[str, Any],
    harness: dict[str, Any],
    *,
    max_environment_actions: int,
    max_spend_usd: float = 0.0,
) -> tuple[bool, str | None]:
    """配对是否有效：双方需完成可比较的 episode（非 failed/timeout/基础设施错误）。"""
    for row in (baseline, harness):
        if row.get("status") == "failed":
            return False, f"{row['agent']}_failed"
        if row.get("error"):
            return False, f"{row['agent']}_error"
        if row.get("status") == "timeout":
            return False, f"{row['agent']}_timeout"

    baseline_actions = int(baseline.get("environment_actions", 0))
    harness_actions = int(harness.get("environment_actions", 0))
    baseline_status = str(baseline.get("status", ""))
    harness_status = str(harness.get("status", ""))

    both_exhausted = (
        baseline_status in VALID_BUDGET_TERMINAL
        and harness_status in VALID_BUDGET_TERMINAL
        and (
            baseline_status != "action_budget_exhausted"
            or baseline_actions == max_environment_actions
        )
        and (
            harness_status != "action_budget_exhausted"
            or harness_actions == max_environment_actions
        )
    )
    if both_exhausted:
        return True, None

    if baseline_status in VALID_SPEND_TERMINAL and harness_status in VALID_SPEND_TERMINAL:
        baseline_cost = float((baseline.get("usage") or {}).get("estimated_cost_usd") or 0.0)
        harness_cost = float((harness.get("usage") or {}).get("estimated_cost_usd") or 0.0)
        tolerance = max(0.25, max_spend_usd * 0.05)
        if abs(baseline_cost - harness_cost) <= tolerance:
            return True, None
        return False, "unequal_spend_budget"

    success = VALID_SUCCESS_TERMINAL
    budget = VALID_BUDGET_TERMINAL
    if baseline_status in success and harness_status in success | budget:
        return True, None
    if harness_status in success and baseline_status in success | budget:
        return True, None
    return False, "incomparable_terminals"


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """按 agent 聚合指标均值/标准差，写入 experiment.json 的 summary。"""
    output: dict[str, Any] = {}
    for agent_name in ("baseline", "harness"):
        rows = [row for row in results if row["agent"] == agent_name]
        output[agent_name] = {
            "runs": len(rows),
            "completion_rate": (
                sum(bool(row["completed"]) for row in rows) / len(rows) if rows else 0.0
            ),
            "score": _mean_stdev([float(row["score"]) for row in rows]),
            "levels_completed": _mean_stdev([float(row["levels_completed"]) for row in rows]),
            "environment_actions": _mean_stdev([float(row["environment_actions"]) for row in rows]),
            "exploration_actions": _mean_stdev(
                [float(row.get("exploration_actions", 0)) for row in rows]
            ),
            "navigation_actions": _mean_stdev(
                [float(row.get("navigation_actions", 0)) for row in rows]
            ),
            "planned_actions": _mean_stdev([float(row.get("planned_actions", 0)) for row in rows]),
            "fallback_actions": _mean_stdev(
                [float(row.get("fallback_actions", 0)) for row in rows]
            ),
            "baseline_batches": _mean_stdev(
                [float(row.get("baseline_batches", 0)) for row in rows]
            ),
            "baseline_actions_proposed": _mean_stdev(
                [float(row.get("baseline_actions_proposed", 0)) for row in rows]
            ),
            "baseline_batches_truncated": _mean_stdev(
                [float(row.get("baseline_batches_truncated", 0)) for row in rows]
            ),
            "model_calls": _mean_stdev([float(row["model_calls"]) for row in rows]),
            "total_tokens": _mean_stdev([float(row["usage"]["total_tokens"]) for row in rows]),
            "reasoning_tokens": _mean_stdev(
                [float(row["usage"].get("reasoning_tokens", 0)) for row in rows]
            ),
            "cached_prompt_tokens": _mean_stdev(
                [float(row["usage"].get("cached_prompt_tokens", 0)) for row in rows]
            ),
            "wall_clock_seconds": _mean_stdev([float(row["wall_clock_seconds"]) for row in rows]),
            "backtest_failures": sum(row["backtest_failures"] for row in rows),
            "prediction_mismatches": sum(row["prediction_mismatches"] for row in rows),
            "prequential_predictions": sum(row.get("prequential_predictions", 0) for row in rows),
            "prequential_matches": sum(row.get("prequential_matches", 0) for row in rows),
            "prequential_approximate_matches": sum(
                row.get("prequential_approximate_matches", 0) for row in rows
            ),
            "prequential_mismatches": sum(row.get("prequential_mismatches", 0) for row in rows),
            "bfs_plans_generated": sum(row.get("bfs_plans_generated", 0) for row in rows),
            "bfs_derived_planned_actions": sum(
                row.get("bfs_derived_planned_actions", 0) for row in rows
            ),
            "bfs_no_plan_results": sum(row.get("bfs_no_plan_results", 0) for row in rows),
            "bfs_no_plan_cache_hits": sum(row.get("bfs_no_plan_cache_hits", 0) for row in rows),
            "discriminating_experiments": sum(
                row.get("discriminating_experiments", 0) for row in rows
            ),
            "experiments_observed": sum(row.get("experiments_observed", 0) for row in rows),
            "experiments_resolved": sum(row.get("experiments_resolved", 0) for row in rows),
            "hypothesis_revisions": sum(row.get("hypothesis_revisions", 0) for row in rows),
            "wm_complexity_rejections": sum(row.get("wm_complexity_rejections", 0) for row in rows),
            "event_driven_deliberations": sum(
                row.get("event_driven_deliberations", 0) for row in rows
            ),
            "max_deliberation_context_chars": max(
                (row.get("max_deliberation_context_chars", 0) for row in rows),
                default=0,
            ),
            "failures": sum(row["status"] == "failed" for row in rows),
        }
        costs = [
            row["usage"]["estimated_cost_usd"]
            for row in rows
            if row["usage"]["estimated_cost_usd"] is not None
        ]
        output[agent_name]["estimated_cost_usd"] = (
            _mean_stdev([float(cost) for cost in costs])
            if len(costs) == len(rows) and rows
            else None
        )

    paired: list[tuple[dict[str, Any], dict[str, Any]]] = []
    valid_paired: list[tuple[dict[str, Any], dict[str, Any]]] = []
    invalid_reasons: list[str] = []
    for run_index in sorted({int(row["run_index"]) for row in results}):
        rows = [row for row in results if int(row["run_index"]) == run_index]
        baseline = next((row for row in rows if row["agent"] == "baseline"), None)
        harness = next((row for row in rows if row["agent"] == "harness"), None)
        if baseline is None or harness is None:
            continue
        paired.append((baseline, harness))
        if baseline.get("paired_valid") is True:
            valid_paired.append((baseline, harness))
        elif baseline.get("paired_valid") is False:
            reason = baseline.get("paired_invalid_reason") or "unspecified"
            invalid_reasons.append(str(reason))
        else:
            budget = max(
                int(baseline.get("environment_actions", 0)),
                int(harness.get("environment_actions", 0)),
            )
            valid, reason = pair_validity(baseline, harness, max_environment_actions=budget)
            if valid:
                valid_paired.append((baseline, harness))
            elif reason:
                invalid_reasons.append(reason)

    ability_pairs = valid_paired
    output["comparison"] = {
        "paired_runs": len(paired),
        "paired_valid_runs": len(ability_pairs),
        "paired_invalid_reasons": invalid_reasons,
        "harness_minus_baseline": {
            field: _mean_stdev(
                [
                    float(harness[field]) - float(baseline[field])
                    for baseline, harness in ability_pairs
                ]
            )
            for field in (
                "score",
                "levels_completed",
                "environment_actions",
                "model_calls",
                "wall_clock_seconds",
            )
        },
        "completion_rate_difference": (
            statistics.fmean(
                [
                    float(harness["completed"]) - float(baseline["completed"])
                    for baseline, harness in ability_pairs
                ]
            )
            if ability_pairs
            else None
        ),
        "ability_sample_note": (
            "only paired_valid runs contribute to ability deltas; "
            "invalid pairs are infrastructure/gate failures, not 0% ability samples"
        ),
    }
    return output


def run_experiment(
    config: ExperimentConfig,
    environment_factory: EnvironmentFactory,
    client_factory: ClientFactory,
    *,
    agents: tuple[str, ...] | None = None,
) -> Path:
    """跑完整实验目录：逐 seed/run 调用 run_agent，写 journal 与 experiment.json。"""
    experiment_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    root = config.output_dir / experiment_id
    root.mkdir(parents=True, exist_ok=False)
    selected = agents or ("baseline", "harness")
    for name in selected:
        if name not in {"baseline", "harness"}:
            raise ValueError(f"unsupported agent {name}; expected baseline|harness")
    document: dict[str, Any] = {
        "experiment_id": experiment_id,
        "created_at": datetime.now(UTC).isoformat(),
        "config": {**config.public_dict(), "agents": list(selected)},
        "results": [],
        "aggregate": {},
        "experiment_spend": {
            "cap_usd": config.experiment_max_spend_usd,
            "estimated_cost_usd": 0.0,
            "stop_reason": None,
        },
    }
    result_path = root / "experiment.json"
    _atomic_json(result_path, document)
    pending_by_run: dict[int, dict[str, dict[str, Any]]] = {}
    for run_index in range(config.runs):
        if not config.seeds:
            raise ValueError("at least one seed is required")
        seed = config.seeds[run_index % len(config.seeds)]
        if selected == ("baseline", "harness") or selected == ("harness", "baseline"):
            agent_names = ("baseline", "harness") if run_index % 2 == 0 else ("harness", "baseline")
            agent_names = tuple(name for name in agent_names if name in selected)
        else:
            agent_names = selected
        for agent_name in agent_names:
            spent_so_far = sum(
                float((row.get("usage") or {}).get("estimated_cost_usd") or 0.0)
                for row in document["results"]
            )
            document["experiment_spend"]["estimated_cost_usd"] = spent_so_far
            effective_config = config
            if config.experiment_max_spend_usd > 0:
                remaining = config.experiment_max_spend_usd - spent_so_far
                if remaining <= config.request_spend_reserve_usd:
                    document["experiment_spend"]["stop_reason"] = "experiment_spend_reserve_reached"
                    document["aggregate"] = aggregate(document["results"])
                    _atomic_json(result_path, document)
                    return result_path
                run_cap = (
                    min(config.max_spend_usd, remaining) if config.max_spend_usd > 0 else remaining
                )
                effective_config = replace(config, max_spend_usd=run_cap)
            journal_path = root / f"{agent_name}-run-{run_index}.jsonl"
            started = time.monotonic()
            try:
                client = client_factory()
                if agent_name == "baseline":
                    agent = BaselineAgent(client, effective_config)
                else:
                    agent = make_harness_agent(client, effective_config)
                environment = environment_factory(seed)
                metrics = run_agent(
                    agent,
                    environment,
                    effective_config,
                    run_index,
                    seed,
                    journal_path,
                )
            except Exception as exc:
                metrics = RunMetrics(
                    agent=agent_name,
                    game_id=config.game_id,
                    run_index=run_index,
                    seed=seed,
                    status="failed",
                    wall_clock_seconds=time.monotonic() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )
                AppendOnlyJournal(journal_path).append(
                    "run_setup_failed",
                    {
                        "agent": agent_name,
                        "run_index": run_index,
                        "seed": seed,
                        "error": metrics.error,
                    },
                )
            row = asdict(metrics)
            row["effective_max_spend_usd"] = effective_config.max_spend_usd
            pending_by_run.setdefault(run_index, {})[agent_name] = row
            document["results"].append(row)
            if {"baseline", "harness"} <= set(pending_by_run[run_index]):
                baseline = pending_by_run[run_index]["baseline"]
                harness = pending_by_run[run_index]["harness"]
                valid, reason = pair_validity(
                    baseline,
                    harness,
                    max_environment_actions=config.max_environment_actions,
                    max_spend_usd=config.max_spend_usd,
                )
                for item in document["results"]:
                    if int(item["run_index"]) != run_index:
                        continue
                    item["paired_valid"] = valid
                    item["paired_invalid_reason"] = reason
            elif len(selected) == 1:
                for item in document["results"]:
                    if int(item["run_index"]) != run_index:
                        continue
                    item["paired_valid"] = None
                    item["paired_invalid_reason"] = "single_agent_run"
            document["aggregate"] = aggregate(document["results"])
            document["experiment_spend"]["estimated_cost_usd"] = sum(
                float((item.get("usage") or {}).get("estimated_cost_usd") or 0.0)
                for item in document["results"]
            )
            _atomic_json(result_path, document)
    return result_path
