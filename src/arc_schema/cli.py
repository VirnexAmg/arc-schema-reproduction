from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from arc_schema.config import ExperimentConfig
from arc_schema.context import frame_png_base64
from arc_schema.core import Action
from arc_schema.deepseek_client import DeepSeekClient, ModelRequestError
from arc_schema.environment import ArcEnvironmentFactory
from arc_schema.evaluation import run_experiment
from arc_schema.mock import DeterministicMockClient, ToyEnvironment


def _configured(args: argparse.Namespace, *, game_id: str | None = None) -> ExperimentConfig:
    config = ExperimentConfig.from_env()
    updates: dict = {
        "game_id": game_id or config.game_id,
        "runs": args.runs if args.runs is not None else config.runs,
        "max_environment_actions": (
            args.max_actions if args.max_actions is not None else config.max_environment_actions
        ),
        "output_dir": Path(args.output) if args.output else config.output_dir,
    }
    if getattr(args, "explore_steps", None) is not None:
        updates["explore_steps"] = args.explore_steps
    if getattr(args, "run_timeout", None) is not None:
        updates["run_timeout_seconds"] = args.run_timeout
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
                        'Describe whether you can see a grid image. '
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
            config.runs * config.deliberation_max_turns * max(config.max_environment_actions // 2, 1)
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


def _real_ab(args: argparse.Namespace) -> int:
    config = _configured(args)
    agents = tuple(
        part.strip()
        for part in str(getattr(args, "agents", "baseline,harness")).split(",")
        if part.strip()
    )
    logical_calls, api_attempts = _estimate_call_bound(config)
    if agents == ("harness",):
        logical_calls = config.runs * config.deliberation_max_turns * max(
            config.max_environment_actions // 2, 1
        )
        api_attempts = logical_calls * (config.model.max_retries + 1)
    elif agents == ("baseline",):
        logical_calls = config.runs * config.max_environment_actions
        api_attempts = logical_calls * (config.model.max_retries + 1)
    print(
        "成本风险上界：最多 "
        f"{logical_calls} 次逻辑模型调用、{api_attempts} 次含重试 API 尝试；"
        f"单局硬超时 {config.run_timeout_seconds}s；"
        f"harness_mode={config.harness_mode}；"
        f"agents={','.join(agents)}；"
        f"deliberation_max_turns={config.deliberation_max_turns}；"
        f"max_spend_usd={config.max_spend_usd or 'unlimited'}；"
        f"model={config.model.model}；"
        f"reasoning_effort={config.model.reasoning_effort}；"
        "实际 token 与费用取决于历史长度和供应商定价。"
    )
    if not args.confirm_api_cost_risk:
        raise SystemExit("未执行真实 API。确认范围后请显式添加 --confirm-api-cost-risk。")
    config.model.validate_real()
    factory = ArcEnvironmentFactory(config.game_id, config.arc_operation_mode, config.render_mode)
    result = run_experiment(
        config,
        environment_factory=factory.create,
        client_factory=lambda: DeepSeekClient(config.model),
        agents=agents,
    )
    print(result)
    return 0


def _add_limits(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs", type=int)
    parser.add_argument("--max-actions", type=int)
    parser.add_argument("--output")
    parser.add_argument("--explore-steps", type=int)
    parser.add_argument("--run-timeout", type=float)


def main() -> int:
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

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
