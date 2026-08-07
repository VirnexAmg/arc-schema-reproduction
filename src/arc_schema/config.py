from __future__ import annotations

"""
实验与模型配置：从环境变量 / .env 装载预算、runtime 与模型参数。

阅读导引：
- ModelConfig：模型端点、effort、vision、context_transitions、单价（算 notional）
- ExperimentConfig：动作/调用/token/reserve/notional/墙钟等停止边界
- from_env()：OpenAI/Codex 路径下 model.seed 固定为 None；DeepSeek 可读 DEEPSEEK_SEED
- agent_runtime：chat_json（旧工具环）vs codex_cli（当前主线）
"""

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


def _strip_key_envs() -> None:
    for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        if name in os.environ:
            os.environ[name] = os.environ[name].strip()
    if Path(".env").exists():
        from dotenv import dotenv_values

        values = dotenv_values(".env")
        for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
            if not os.environ.get(name) and values.get(name):
                os.environ[name] = str(values[name]).strip()


@dataclass(frozen=True)
class ModelConfig:
    """单模型调用参数。注意：Codex/OpenAI 路径下 seed 常为 None（不固定采样种子）。"""

    base_url: str = "https://api.deepseek.com"
    model: str = ""
    thinking_mode: str = "disabled"
    reasoning_effort: str = "high"
    temperature: float = 0.0
    timeout_seconds: float = 60.0
    max_retries: int = 1
    seed: int | None = 0  # 模型采样 seed；与 ExperimentConfig.seeds（关卡 seed）不同
    max_output_tokens: int = 4096
    baseline_max_output_tokens: int = 512
    world_model_max_output_tokens: int = 4096
    context_transitions: int = 12  # 塞进模型上下文的历史转移条数上限
    vision_enabled: bool = False
    api_key_env: str = "DEEPSEEK_API_KEY"
    input_cost_per_million: float | None = None
    cached_input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None

    def validate_real(self) -> None:
        has_key = bool(
            os.environ.get(self.api_key_env, "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
            or os.environ.get("DEEPSEEK_API_KEY", "").strip()
        )
        if not has_key:
            raise ValueError(
                "API key required (OPENAI_API_KEY for gpt-5.6-sol, or DEEPSEEK_API_KEY)"
            )
        if not self.model:
            raise ValueError("model id is required; never guessed")
        if self.thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("thinking_mode must be enabled or disabled")
        allowed_effort = {"none", "low", "medium", "high", "xhigh", "max", "disabled"}
        if self.reasoning_effort not in allowed_effort:
            raise ValueError(
                "reasoning_effort must be one of none|low|medium|high|xhigh|max|disabled"
            )

    def max_tokens_for(self, purpose: str) -> int:
        if purpose == "baseline_action":
            return self.baseline_max_output_tokens
        if purpose in {"world_model", "deliberation"}:
            return self.world_model_max_output_tokens
        if purpose == "vision_smoke":
            return min(self.baseline_max_output_tokens, 512)
        return self.max_output_tokens


@dataclass(frozen=True)
class ExperimentConfig:
    """一次实验的全局边界。0 通常表示该维预算关闭（不限）。"""

    # chat_json=旧 JSON 工具环（消融）；codex_cli=主线持久编码代理线程。
    agent_runtime: str = "chat_json"
    game_id: str = "ls20"
    runs: int = 1
    max_environment_actions: int = 10
    # 仅 baseline：1=每调用一步；2..16=batched direct，仍无 Schema 能力。
    baseline_max_batch_actions: int = 1
    seeds: tuple[int, ...] = (0,)  # 关卡/环境 seed，不是模型采样 seed
    output_dir: Path = Path("runs")
    arc_operation_mode: str = "offline"
    render_mode: str | None = None
    planner_max_nodes: int = 1_000
    harness_model_attempts: int = 2
    explore_steps: int = 6
    max_plan_steps: int = 3  # planned/navigation burst 最大步数
    explore_burst: int = 3
    wm_time_reserve_seconds: float = 120.0
    run_timeout_seconds: float = 600.0  # 墙钟上限（秒）
    max_model_calls_per_run: int = 40
    harness_mode: str = "schema"  # schema=程序 WM；fsm=旧声明式消融
    deliberation_max_turns: int = 8
    max_spend_usd: float = 0.0
    request_spend_reserve_usd: float = 0.75
    experiment_max_spend_usd: float = 0.0
    auto_reset_on_game_over: bool = True
    max_game_over_resets: int = 20
    schema_commit_only: bool = False  # True 时强制只走 commit，不做盲探索填预算
    allow_approximate_visual_matches: bool = False  # True 时允许 approximate 认证→仅 navigation
    target_levels_completed: int = 0
    max_total_tokens_per_run: int = 0
    max_uncached_tokens_per_run: int = 0
    max_output_tokens_per_run: int = 0
    token_reserve_per_call: int = 0  # 再开一次调用前预留的 total tokens
    max_notional_cost_usd: float = 0.0
    codex_executable: str = "codex"
    codex_cli_timeout_seconds: float = 900.0
    codex_post_turn_exit_grace_seconds: float = 10.0
    # Context policy is an experimental treatment, not an implicit Codex default:
    # persistent=one thread per game/run; adaptive=checkpoint/roll at token watermarks;
    # fixed_turns=legacy fixed-call rollover ablation.
    codex_context_policy: str = "persistent"
    codex_max_turns_per_thread: int = 4
    codex_soft_context_prompt_tokens: int = 220_000
    codex_hard_context_prompt_tokens: int = 350_000
    codex_rollover_on_level_boundary: bool = False
    codex_compound_cycle: bool = True  # 允许 schema_cycle 一回合闭环
    model: ModelConfig = field(default_factory=ModelConfig)

    @classmethod
    def from_env(cls) -> ExperimentConfig:
        # Prefer .env over stale shell exports (e.g. old DEEPSEEK_BASE_URL).
        # A one-process experiment can explicitly opt out so its preregistered
        # caps override the developer's persistent .env without editing it.
        dotenv_override = _optional_bool("ARC_DOTENV_OVERRIDE", True)
        load_dotenv(override=dotenv_override)
        _strip_key_envs()
        seed_text = os.getenv("ARC_SCHEMA_SEEDS", "0")
        provider = os.getenv("ARC_MODEL_PROVIDER", "").strip().lower()
        use_openai = provider == "openai"

        if use_openai:
            model = ModelConfig(
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.openai.com/v1"),
                model=os.getenv("DEEPSEEK_MODEL", "gpt-5.6-sol"),
                thinking_mode=os.getenv("DEEPSEEK_THINKING_MODE", "disabled").lower(),
                reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT", "medium").lower(),
                temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0")),
                timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "180")),
                max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "1")),
                seed=None,
                max_output_tokens=int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "8192")),
                baseline_max_output_tokens=int(
                    os.getenv("DEEPSEEK_BASELINE_MAX_OUTPUT_TOKENS", "1024")
                ),
                world_model_max_output_tokens=int(
                    os.getenv("DEEPSEEK_WORLD_MODEL_MAX_OUTPUT_TOKENS", "8192")
                ),
                context_transitions=int(os.getenv("DEEPSEEK_CONTEXT_TRANSITIONS", "16")),
                vision_enabled=_optional_bool("DEEPSEEK_VISION_ENABLED", False),
                api_key_env=os.getenv("ARC_API_KEY_ENV", "OPENAI_API_KEY"),
                input_cost_per_million=float(os.getenv("DEEPSEEK_INPUT_COST_PER_MILLION", "5.0")),
                cached_input_cost_per_million=float(
                    os.getenv("DEEPSEEK_CACHED_INPUT_COST_PER_MILLION", "0.5")
                ),
                output_cost_per_million=float(
                    os.getenv("DEEPSEEK_OUTPUT_COST_PER_MILLION", "30.0")
                ),
            )
        else:
            seed_raw = os.getenv("DEEPSEEK_SEED", "0")
            model = ModelConfig(
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=os.getenv("DEEPSEEK_MODEL", ""),
                thinking_mode=os.getenv("DEEPSEEK_THINKING_MODE", "disabled").lower(),
                reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT", "high").lower(),
                temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0")),
                timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60")),
                max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "1")),
                seed=int(seed_raw) if seed_raw else None,
                max_output_tokens=int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "4096")),
                baseline_max_output_tokens=int(
                    os.getenv("DEEPSEEK_BASELINE_MAX_OUTPUT_TOKENS", "512")
                ),
                world_model_max_output_tokens=int(
                    os.getenv("DEEPSEEK_WORLD_MODEL_MAX_OUTPUT_TOKENS", "4096")
                ),
                context_transitions=int(os.getenv("DEEPSEEK_CONTEXT_TRANSITIONS", "12")),
                vision_enabled=_optional_bool("DEEPSEEK_VISION_ENABLED", False),
                api_key_env=os.getenv("ARC_API_KEY_ENV", "DEEPSEEK_API_KEY"),
                input_cost_per_million=_optional_float("DEEPSEEK_INPUT_COST_PER_MILLION"),
                cached_input_cost_per_million=_optional_float(
                    "DEEPSEEK_CACHED_INPUT_COST_PER_MILLION"
                ),
                output_cost_per_million=_optional_float("DEEPSEEK_OUTPUT_COST_PER_MILLION"),
            )

        render = os.getenv("ARC_RENDER_MODE", "").strip() or None
        return cls(
            agent_runtime=os.getenv("ARC_AGENT_RUNTIME", "chat_json").strip().lower(),
            game_id=os.getenv("ARC_GAME_ID", "ls20"),
            runs=int(os.getenv("ARC_RUNS", "1")),
            max_environment_actions=int(os.getenv("ARC_MAX_ENVIRONMENT_ACTIONS", "10")),
            baseline_max_batch_actions=int(os.getenv("ARC_BASELINE_MAX_BATCH_ACTIONS", "1")),
            seeds=tuple(int(item.strip()) for item in seed_text.split(",") if item.strip()),
            output_dir=Path(os.getenv("ARC_OUTPUT_DIR", "runs")),
            arc_operation_mode=os.getenv("ARC_OPERATION_MODE", "offline").lower(),
            render_mode=render,
            planner_max_nodes=int(os.getenv("ARC_PLANNER_MAX_NODES", "5000")),
            harness_model_attempts=int(os.getenv("ARC_HARNESS_MODEL_ATTEMPTS", "2")),
            explore_steps=int(os.getenv("ARC_EXPLORE_STEPS", "6")),
            max_plan_steps=int(os.getenv("ARC_MAX_PLAN_STEPS", "16")),
            explore_burst=int(os.getenv("ARC_EXPLORE_BURST", "3")),
            wm_time_reserve_seconds=float(os.getenv("ARC_WM_TIME_RESERVE_SECONDS", "180")),
            run_timeout_seconds=float(os.getenv("ARC_RUN_TIMEOUT_SECONDS", "1800")),
            max_model_calls_per_run=int(os.getenv("ARC_MAX_MODEL_CALLS_PER_RUN", "120")),
            harness_mode=os.getenv("ARC_HARNESS_MODE", "schema").lower(),
            deliberation_max_turns=int(os.getenv("ARC_DELIBERATION_MAX_TURNS", "16")),
            max_spend_usd=float(os.getenv("ARC_MAX_SPEND_USD", "0")),
            request_spend_reserve_usd=float(os.getenv("ARC_REQUEST_SPEND_RESERVE_USD", "0.75")),
            experiment_max_spend_usd=float(os.getenv("ARC_EXPERIMENT_MAX_SPEND_USD", "0")),
            auto_reset_on_game_over=_optional_bool("ARC_AUTO_RESET_ON_GAME_OVER", True),
            max_game_over_resets=int(os.getenv("ARC_MAX_GAME_OVER_RESETS", "20")),
            schema_commit_only=_optional_bool("ARC_SCHEMA_COMMIT_ONLY", False),
            allow_approximate_visual_matches=_optional_bool(
                "ARC_ALLOW_APPROXIMATE_VISUAL_MATCHES", False
            ),
            target_levels_completed=int(os.getenv("ARC_TARGET_LEVELS_COMPLETED", "0")),
            max_total_tokens_per_run=int(os.getenv("ARC_MAX_TOTAL_TOKENS_PER_RUN", "0")),
            max_uncached_tokens_per_run=int(os.getenv("ARC_MAX_UNCACHED_TOKENS_PER_RUN", "0")),
            max_output_tokens_per_run=int(os.getenv("ARC_MAX_OUTPUT_TOKENS_PER_RUN", "0")),
            token_reserve_per_call=int(os.getenv("ARC_TOKEN_RESERVE_PER_CALL", "0")),
            max_notional_cost_usd=float(os.getenv("ARC_MAX_NOTIONAL_COST_USD", "0")),
            codex_executable=os.getenv("ARC_CODEX_EXECUTABLE", "codex").strip(),
            codex_cli_timeout_seconds=float(os.getenv("ARC_CODEX_CLI_TIMEOUT_SECONDS", "900")),
            codex_post_turn_exit_grace_seconds=float(
                os.getenv("ARC_CODEX_POST_TURN_EXIT_GRACE_SECONDS", "10")
            ),
            codex_context_policy=os.getenv("ARC_CODEX_CONTEXT_POLICY", "persistent")
            .strip()
            .lower(),
            codex_max_turns_per_thread=int(os.getenv("ARC_CODEX_MAX_TURNS_PER_THREAD", "4")),
            codex_soft_context_prompt_tokens=int(
                os.getenv("ARC_CODEX_SOFT_CONTEXT_PROMPT_TOKENS", "220000")
            ),
            codex_hard_context_prompt_tokens=int(
                os.getenv(
                    "ARC_CODEX_HARD_CONTEXT_PROMPT_TOKENS",
                    # Backward-compatible read of the old, ambiguously named setting.
                    os.getenv("ARC_CODEX_ROLLOVER_PROMPT_TOKENS", "350000"),
                )
            ),
            codex_rollover_on_level_boundary=_optional_bool(
                "ARC_CODEX_ROLLOVER_ON_LEVEL_BOUNDARY", False
            ),
            codex_compound_cycle=_optional_bool("ARC_CODEX_COMPOUND_CYCLE", True),
            model=model,
        )

    def public_dict(self) -> dict[str, Any]:
        """Serializable configuration guaranteed not to contain the API key."""
        value = asdict(self)
        value["output_dir"] = str(self.output_dir)
        return value
