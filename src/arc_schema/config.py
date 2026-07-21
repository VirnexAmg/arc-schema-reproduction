from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _optional_float(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value not in (None, "") else None


def _optional_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = "https://api.deepseek.com"
    model: str = ""
    thinking_mode: str = "disabled"
    reasoning_effort: str = "high"
    temperature: float = 0.0
    timeout_seconds: float = 60.0
    max_retries: int = 1
    seed: int | None = 0
    max_output_tokens: int = 4096
    baseline_max_output_tokens: int = 512
    world_model_max_output_tokens: int = 4096
    context_transitions: int = 12
    vision_enabled: bool = False
    input_cost_per_million: float | None = None
    cached_input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None

    def validate_real(self) -> None:
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise ValueError("DEEPSEEK_API_KEY is required for a real model run")
        if not self.model:
            raise ValueError("DEEPSEEK_MODEL is required; the model ID is never guessed")
        if self.thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("DEEPSEEK_THINKING_MODE must be enabled or disabled")
        if self.reasoning_effort not in {"high", "max"}:
            raise ValueError("DEEPSEEK_REASONING_EFFORT must be high or max")

    def max_tokens_for(self, purpose: str) -> int:
        if purpose == "baseline_action":
            return self.baseline_max_output_tokens
        if purpose in {"world_model", "vision_smoke"}:
            return (
                self.world_model_max_output_tokens
                if purpose == "world_model"
                else min(self.baseline_max_output_tokens, 512)
            )
        return self.max_output_tokens


@dataclass(frozen=True)
class ExperimentConfig:
    game_id: str = "ls20"
    runs: int = 1
    max_environment_actions: int = 10
    seeds: tuple[int, ...] = (0,)
    output_dir: Path = Path("runs")
    arc_operation_mode: str = "offline"
    render_mode: str | None = None
    planner_max_nodes: int = 1_000
    harness_model_attempts: int = 2
    explore_steps: int = 6
    max_plan_steps: int = 3
    run_timeout_seconds: float = 600.0
    max_model_calls_per_run: int = 40
    model: ModelConfig = field(default_factory=ModelConfig)

    @classmethod
    def from_env(cls) -> ExperimentConfig:
        load_dotenv()
        seed_text = os.getenv("ARC_SCHEMA_SEEDS", "0")
        model = ModelConfig(
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("DEEPSEEK_MODEL", ""),
            thinking_mode=os.getenv("DEEPSEEK_THINKING_MODE", "disabled").lower(),
            reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT", "high").lower(),
            temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0")),
            timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "1")),
            seed=int(os.getenv("DEEPSEEK_SEED", "0")) if os.getenv("DEEPSEEK_SEED", "0") else None,
            max_output_tokens=int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "4096")),
            baseline_max_output_tokens=int(
                os.getenv("DEEPSEEK_BASELINE_MAX_OUTPUT_TOKENS", "512")
            ),
            world_model_max_output_tokens=int(
                os.getenv("DEEPSEEK_WORLD_MODEL_MAX_OUTPUT_TOKENS", "4096")
            ),
            context_transitions=int(os.getenv("DEEPSEEK_CONTEXT_TRANSITIONS", "12")),
            vision_enabled=_optional_bool("DEEPSEEK_VISION_ENABLED", False),
            input_cost_per_million=_optional_float("DEEPSEEK_INPUT_COST_PER_MILLION"),
            cached_input_cost_per_million=_optional_float(
                "DEEPSEEK_CACHED_INPUT_COST_PER_MILLION"
            ),
            output_cost_per_million=_optional_float("DEEPSEEK_OUTPUT_COST_PER_MILLION"),
        )
        render = os.getenv("ARC_RENDER_MODE", "").strip() or None
        return cls(
            game_id=os.getenv("ARC_GAME_ID", "ls20"),
            runs=int(os.getenv("ARC_RUNS", "1")),
            max_environment_actions=int(os.getenv("ARC_MAX_ENVIRONMENT_ACTIONS", "10")),
            seeds=tuple(int(item.strip()) for item in seed_text.split(",") if item.strip()),
            output_dir=Path(os.getenv("ARC_OUTPUT_DIR", "runs")),
            arc_operation_mode=os.getenv("ARC_OPERATION_MODE", "offline").lower(),
            render_mode=render,
            planner_max_nodes=int(os.getenv("ARC_PLANNER_MAX_NODES", "1000")),
            harness_model_attempts=int(os.getenv("ARC_HARNESS_MODEL_ATTEMPTS", "2")),
            explore_steps=int(os.getenv("ARC_EXPLORE_STEPS", "6")),
            max_plan_steps=int(os.getenv("ARC_MAX_PLAN_STEPS", "3")),
            run_timeout_seconds=float(os.getenv("ARC_RUN_TIMEOUT_SECONDS", "600")),
            max_model_calls_per_run=int(os.getenv("ARC_MAX_MODEL_CALLS_PER_RUN", "40")),
            model=model,
        )

    def public_dict(self) -> dict[str, Any]:
        """Serializable configuration guaranteed not to contain the API key."""
        value = asdict(self)
        value["output_dir"] = str(self.output_dir)
        return value
