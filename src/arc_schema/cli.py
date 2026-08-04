from __future__ import annotations

"""
命令行入口：mock A/B、真实实验、Codex C0.5、smoke 等子命令。

阅读导引（建议最后读）：
- main()：argparse 子命令分发
- _real_ab / _mock_ab：配对或单臂实验入口
- _codex_c05：Toy 闭环验收
- _configured：把 CLI 参数叠到 ExperimentConfig.from_env()
理解主线后再看这里，避免被 CLI 细节淹没。
"""

import argparse
import json
import shutil
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from arc_schema.config import ExperimentConfig
from arc_schema.codex_cli_client import CodexCliClient
from arc_schema.c05_validation import c05_config, run_c05
from arc_schema.context import frame_png_base64
from arc_schema.core import Action
from arc_schema.deepseek_client import DeepSeekClient, ModelRequestError
from arc_schema.environment import ArcEnvironmentFactory
from arc_schema.evaluation import run_experiment
from arc_schema.mock import DeterministicMockClient, ToyEnvironment


def _configured(args: argparse.Namespace, *, game_id: str | None = None) -> ExperimentConfig:
    config = ExperimentConfig.from_env()
    runs_arg = getattr(args, "runs", None)
    actions_arg = getattr(args, "max_actions", None)
    output_arg = getattr(args, "output", None)
    updates: dict = {
        "game_id": game_id or config.game_id,
        "runs": runs_arg if runs_arg is not None else config.runs,
        "max_environment_actions": (
            actions_arg if actions_arg is not None else config.max_environment_actions
        ),
        "output_dir": Path(output_arg) if output_arg else config.output_dir,
    }
    if getattr(args, "explore_steps", None) is not None:
        updates["explore_steps"] = args.explore_steps
    if getattr(args, "run_timeout", None) is not None:
        updates["run_timeout_seconds"] = args.run_timeout
    if getattr(args, "max_spend", None) is not None:
        updates["max_spend_usd"] = args.max_spend
    if getattr(args, "experiment_max_spend", None) is not None:
        updates["experiment_max_spend_usd"] = args.experiment_max_spend
    if getattr(args, "request_spend_reserve", None) is not None:
        updates["request_spend_reserve_usd"] = args.request_spend_reserve
    if getattr(args, "max_model_calls", None) is not None:
        updates["max_model_calls_per_run"] = args.max_model_calls
    if getattr(args, "max_notional_cost", None) is not None:
        updates["max_notional_cost_usd"] = args.max_notional_cost
    return replace(config, **updates)


def _mock_ab(args: argparse.Namespace) -> int:
    config = _configured(args, game_id="toy")
    result = run_experiment(
        config,
        environment_factory=lambda seed: ToyEnvironment(),
        client_factory=DeterministicMockClient,
    )
    print(result)
    return 0


def _arc_smoke(args: argparse.Namespace) -> int:
    config = _configured(args)
    factory = ArcEnvironmentFactory(config.game_id, config.arc_operation_mode, config.render_mode)
    environment = factory.create(config.seeds[0])
    initial = environment.current
    action = Action(id=initial.available_actions[0])
    after = environment.step(action)
    print(
        json.dumps(
            {
                "game_id": after.game_id,
                "action_id": action.id,
                "state": after.state,
                "levels_completed": after.levels_completed,
                "available_actions": list(after.available_actions),
                "frame_fingerprint": after.fingerprint,
                "score": environment.score_summary(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _vision_smoke(args: argparse.Namespace) -> int:
    """Probe whether the endpoint accepts a PNG content-part. No env actions."""
    config = _configured(args)
    config.model.validate_real()
    factory = ArcEnvironmentFactory(config.game_id, config.arc_operation_mode, config.render_mode)
    environment = factory.create(config.seeds[0])
    observation = environment.current
    png = frame_png_base64(observation)
    client = DeepSeekClient(
        replace(
            config.model,
            thinking_mode="disabled",
            baseline_max_output_tokens=512,
            max_output_tokens=512,
        )
    )
    messages = [
        {
            "role": "system",
            "content": "Return one JSON object only.",
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Describe whether you can see a grid image. "
                        'Schema: {"vision_ok":true,"note":"..."}'
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{png}"},
                },
            ],
        },
    ]
    result: dict = {
        "game_id": observation.game_id,
        "fingerprint": observation.fingerprint,
        "vision_accepted": False,
        "fallback": "current_full_rle_plus_history_delta",
    }
    try:
        response = client.complete_json(messages, "vision_smoke")
        result["vision_accepted"] = True
        result["model_value"] = response.value
        result["usage"] = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
            "estimated_cost_usd": response.usage.estimated_cost_usd,
        }
        result["recommended_mode"] = "vision+text"
    except ModelRequestError as exc:
        result["error"] = str(exc)
        result["finish_reason"] = exc.finish_reason
        result["raw_text"] = exc.raw_text[:500]
        result["recommended_mode"] = "rle_delta_fallback"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["recommended_mode"] = "rle_delta_fallback"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("vision_accepted") or "error" in result else 1


def _estimate_call_bound(config: ExperimentConfig) -> tuple[int, int]:
    if config.harness_mode == "schema":
        baseline_calls = config.runs * config.max_environment_actions
        harness_calls = (
            config.runs
            * config.deliberation_max_turns
            * max(config.max_environment_actions // 2, 1)
        )
        logical = baseline_calls + harness_calls
        return logical, logical * (config.model.max_retries + 1)
    baseline_calls = config.runs * config.max_environment_actions
    harness_plan_slots = max(config.max_environment_actions - config.explore_steps, 0)
    burst = max(config.explore_burst, 1)
    harness_replans = (harness_plan_slots + burst - 1) // burst
    harness_calls = config.runs * harness_replans * config.harness_model_attempts
    logical = baseline_calls + harness_calls
    api_attempts = logical * (config.model.max_retries + 1)
    return logical, api_attempts


def _model_client(
    config: ExperimentConfig,
    *,
    direct_action_baseline: bool = False,
):
    if config.agent_runtime == "codex_cli":
        return CodexCliClient(
            config,
            runtime_role=("direct_action_baseline" if direct_action_baseline else "schema"),
        )
    return DeepSeekClient(config.model)


def _codex_executable_available(value: str) -> bool:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.parent != Path("."):
        return candidate.is_file()
    return shutil.which(value) is not None


def _real_ab(args: argparse.Namespace) -> int:
    config = _configured(args)
    if config.agent_runtime not in {"chat_json", "codex_cli"}:
        raise SystemExit("ARC_AGENT_RUNTIME must be chat_json or codex_cli")
    agents = tuple(
        part.strip()
        for part in str(getattr(args, "agents", "baseline,harness")).split(",")
        if part.strip()
    )
    logical_calls, api_attempts = _estimate_call_bound(config)
    if agents == ("harness",):
        logical_calls = config.runs * config.max_model_calls_per_run
        api_attempts = logical_calls * (config.model.max_retries + 1)
    elif agents == ("baseline",):
        per_run_calls = (
            config.max_model_calls_per_run
            if config.agent_runtime == "codex_cli"
            else config.max_environment_actions
        )
        logical_calls = config.runs * per_run_calls
        api_attempts = logical_calls * (config.model.max_retries + 1)
    print(
        "成本风险上界：最多 "
        f"{logical_calls} 次逻辑模型调用、{api_attempts} 次含重试 API 尝试；"
        f"单局硬超时 {config.run_timeout_seconds}s；"
        f"harness_mode={config.harness_mode}；"
        f"agents={','.join(agents)}；"
        f"deliberation_max_turns={config.deliberation_max_turns}；"
        f"max_spend_usd={config.max_spend_usd or 'unlimited'}；"
        f"request_reserve_usd={config.request_spend_reserve_usd}；"
        f"experiment_max_spend_usd={config.experiment_max_spend_usd or 'unlimited'}；"
        f"model={config.model.model}；"
        f"reasoning_effort={config.model.reasoning_effort}；"
        f"vision_enabled={config.model.vision_enabled}；"
        "实际 token 与费用取决于历史长度和供应商定价。"
    )
    if not args.confirm_api_cost_risk:
        raise SystemExit("未执行真实 API。确认范围后请显式添加 --confirm-api-cost-risk。")
    if config.game_id == "ls20" and config.harness_mode == "schema":
        violations = []
        if config.model.model.lower() != "gpt-5.6-sol":
            violations.append("DEEPSEEK_MODEL must be gpt-5.6-sol")
        if not config.model.vision_enabled:
            violations.append("DEEPSEEK_VISION_ENABLED must be true")
        if config.agent_runtime == "codex_cli":
            if agents not in {("harness",), ("baseline",)}:
                violations.append("codex_cli requires a single agent: baseline or harness")
            if config.model.reasoning_effort != "xhigh":
                violations.append("DEEPSEEK_REASONING_EFFORT must be xhigh")
            if not config.schema_commit_only:
                violations.append("ARC_SCHEMA_COMMIT_ONLY must be true")
            if not config.codex_compound_cycle:
                violations.append("ARC_CODEX_COMPOUND_CYCLE must be true")
            if not _codex_executable_available(config.codex_executable):
                violations.append("ARC_CODEX_EXECUTABLE was not found")
            if config.target_levels_completed not in {2, 7}:
                violations.append("ARC_TARGET_LEVELS_COMPLETED must be 2 (C1) or 7 (full run)")
            if config.max_environment_actions <= 0:
                violations.append("ARC_MAX_ENVIRONMENT_ACTIONS must be positive")
            if config.max_model_calls_per_run <= 0:
                violations.append("ARC_MAX_MODEL_CALLS_PER_RUN must be positive")
            if agents == ("baseline",) and not (1 <= config.baseline_max_batch_actions <= 16):
                violations.append("ARC_BASELINE_MAX_BATCH_ACTIONS must be between 1 and 16")
            if config.max_total_tokens_per_run <= 0:
                violations.append("ARC_MAX_TOTAL_TOKENS_PER_RUN must be positive")
            if config.max_uncached_tokens_per_run <= 0:
                violations.append("ARC_MAX_UNCACHED_TOKENS_PER_RUN must be positive")
            if config.max_output_tokens_per_run <= 0:
                violations.append("ARC_MAX_OUTPUT_TOKENS_PER_RUN must be positive")
            if config.token_reserve_per_call <= 0:
                violations.append("ARC_TOKEN_RESERVE_PER_CALL must be positive")
            if (
                config.max_total_tokens_per_run > 0
                and config.token_reserve_per_call >= config.max_total_tokens_per_run
            ):
                violations.append("ARC_TOKEN_RESERVE_PER_CALL must be below the total token cap")
            if config.max_notional_cost_usd <= 0:
                violations.append("ARC_MAX_NOTIONAL_COST_USD must be positive")
            if (
                config.model.input_cost_per_million is None
                or config.model.output_cost_per_million is None
            ):
                violations.append("input/output price rates are required for the notional cap")
            if config.codex_max_turns_per_thread <= 0:
                violations.append("ARC_CODEX_MAX_TURNS_PER_THREAD must be positive")
            if config.codex_post_turn_exit_grace_seconds < 0:
                violations.append("ARC_CODEX_POST_TURN_EXIT_GRACE_SECONDS must be non-negative")
        else:
            if "inferera.com" not in config.model.base_url.lower():
                violations.append("DEEPSEEK_BASE_URL must use Inferera")
            if config.model.reasoning_effort != "medium":
                violations.append("DEEPSEEK_REASONING_EFFORT must be medium")
            if config.model.thinking_mode != "disabled":
                violations.append("DEEPSEEK_THINKING_MODE must be disabled")
            if config.max_spend_usd <= 0:
                violations.append("ARC_MAX_SPEND_USD must be a positive hard cap")
            if config.request_spend_reserve_usd <= 0:
                violations.append("ARC_REQUEST_SPEND_RESERVE_USD must be positive")
        if violations:
            raise SystemExit("ls20 Schema mainline preflight failed:\n- " + "\n- ".join(violations))
    if config.agent_runtime == "codex_cli":
        client_factory = partial(
            _model_client,
            config,
            direct_action_baseline=agents == ("baseline",),
        )
    else:
        config.model.validate_real()
        client_factory = partial(_model_client, config)
    factory = ArcEnvironmentFactory(config.game_id, config.arc_operation_mode, config.render_mode)
    result = run_experiment(
        config,
        environment_factory=factory.create,
        client_factory=client_factory,
        agents=agents,
    )
    print(result)
    return 0


def _codex_c05(args: argparse.Namespace) -> int:
    """Paid-gated real Codex validation on ToyEnvironment, never ARC."""
    base = _configured(args, game_id="toy")
    violations: list[str] = []
    if base.model.model.lower() != "gpt-5.6-sol":
        violations.append("DEEPSEEK_MODEL must be gpt-5.6-sol")
    if base.model.reasoning_effort != "xhigh":
        violations.append("DEEPSEEK_REASONING_EFFORT must be xhigh")
    if not base.model.vision_enabled:
        violations.append("DEEPSEEK_VISION_ENABLED must be true")
    if not base.codex_executable:
        violations.append("ARC_CODEX_EXECUTABLE must identify the standalone CLI")
    elif not _codex_executable_available(base.codex_executable):
        violations.append("ARC_CODEX_EXECUTABLE was not found")
    if violations:
        raise SystemExit("C0.5 preflight failed:\n- " + "\n- ".join(violations))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    root = Path(args.output or "c05-validation") / stamp
    config = c05_config(base, root)
    print(
        "C0.5 风险边界：ToyEnvironment（不调用 ARC）；"
        f"最多 {config.max_model_calls_per_run} 次 Codex Plus 调用；"
        f"reported tokens cap={config.max_total_tokens_per_run}；"
        f"uncached cap={config.max_uncached_tokens_per_run}；"
        f"output cap={config.max_output_tokens_per_run}；"
        f"notional cost cap=${config.max_notional_cost_usd:.2f}；"
        f"timeout={config.run_timeout_seconds}s；model={config.model.model}；"
        f"effort={config.model.reasoning_effort}。"
    )
    if not args.confirm_codex_quota_risk:
        raise SystemExit(
            "未调用模型。确认 C0.5 的 Plus 配额风险后，显式添加 --confirm-codex-quota-risk。"
        )
    version = subprocess.run(
        [config.codex_executable, "--version"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )
    if version.returncode != 0:
        raise SystemExit(f"Codex CLI preflight failed: {version.stderr[-500:]}")
    client = CodexCliClient(config)
    report = run_c05(config, root, client)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


def _add_limits(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs", type=int)
    parser.add_argument("--max-actions", type=int)
    parser.add_argument("--output")
    parser.add_argument("--explore-steps", type=int)
    parser.add_argument("--run-timeout", type=float)
    parser.add_argument("--max-spend", type=float)
    parser.add_argument("--experiment-max-spend", type=float)
    parser.add_argument("--request-spend-reserve", type=float)
    parser.add_argument("--max-model-calls", type=int)
    parser.add_argument("--max-notional-cost", type=float)


def main() -> int:
    """CLI 入口：注册子命令并分派到 mock/真实实验/C0.5/smoke。"""
    parser = argparse.ArgumentParser(prog="arc-schema")
    subparsers = parser.add_subparsers(dest="command", required=True)

    mock_parser = subparsers.add_parser("mock-ab", help="run no-network toy A/B")
    _add_limits(mock_parser)
    mock_parser.set_defaults(handler=_mock_ab)

    smoke_parser = subparsers.add_parser(
        "arc-smoke", help="take one local ARC action without a model API"
    )
    _add_limits(smoke_parser)
    smoke_parser.set_defaults(handler=_arc_smoke)

    vision_parser = subparsers.add_parser(
        "vision-smoke",
        help="one non-thinking API call probing PNG content-parts; no env actions",
    )
    _add_limits(vision_parser)
    vision_parser.set_defaults(handler=_vision_smoke)

    real_parser = subparsers.add_parser("real-ab", help="run controlled ARC + DeepSeek A/B")
    _add_limits(real_parser)
    real_parser.add_argument("--confirm-api-cost-risk", action="store_true")
    real_parser.add_argument(
        "--agents",
        default="baseline,harness",
        help="comma-separated agents: baseline,harness (or either alone)",
    )
    real_parser.set_defaults(handler=_real_ab)

    c05_parser = subparsers.add_parser(
        "codex-c05",
        help="real Codex Plus toy full-loop acceptance; never touches ARC",
    )
    c05_parser.add_argument("--output")
    c05_parser.add_argument("--max-model-calls", type=int, choices=range(1, 5))
    c05_parser.add_argument("--confirm-codex-quota-risk", action="store_true")
    c05_parser.set_defaults(handler=_codex_c05)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
