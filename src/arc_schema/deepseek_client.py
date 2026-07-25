from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI

from arc_schema.config import ModelConfig
from arc_schema.core import Usage


@dataclass(frozen=True)
class ModelResponse:
    value: dict[str, Any]
    raw_text: str
    usage: Usage
    latency_seconds: float
    attempts: int


class ModelClient(Protocol):
    def complete_json(self, messages: list[dict[str, Any]], purpose: str) -> ModelResponse: ...


class ModelRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        attempts: int,
        usage: Usage | None = None,
        raw_text: str = "",
        finish_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.usage = usage or Usage()
        self.raw_text = raw_text
        self.finish_reason = finish_reason


def _parse_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1])
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("model response must be a JSON object")
    return value


def _resolve_api_key(config: ModelConfig) -> str:
    for name in (config.api_key_env, "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise ValueError(
        "API key required: set OPENAI_API_KEY (for gpt-5.6-sol) or DEEPSEEK_API_KEY"
    )


def _is_openai_style(config: ModelConfig) -> bool:
    model = config.model.lower()
    base = config.base_url.lower()
    return (
        "openai.com" in base
        or model.startswith("gpt-")
        or "sol" in model
        or "terra" in model
        or "luna" in model
    )


class OpenAICompatClient:
    """OpenAI-compatible JSON client for DeepSeek and OpenAI (incl. gpt-5.6-sol)."""

    def __init__(self, config: ModelConfig) -> None:
        config.validate_real()
        self.config = config
        self._openai_style = _is_openai_style(config)
        self._client = OpenAI(
            api_key=_resolve_api_key(config),
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=0,
        )

    def complete_json(self, messages: list[dict[str, Any]], purpose: str) -> ModelResponse:
        started = time.monotonic()
        last_error: Exception | None = None
        last_text = ""
        last_finish_reason: str | None = None
        accumulated_usage = Usage()
        max_tokens = self.config.max_tokens_for(purpose)
        for attempt in range(1, self.config.max_retries + 2):
            try:
                kwargs = self._build_request_kwargs(messages, max_tokens)
                response = self._client.chat.completions.create(**kwargs)
                text = response.choices[0].message.content or ""
                last_text = text
                last_finish_reason = response.choices[0].finish_reason
                usage = self._usage_from_response(response)
                accumulated_usage.add(usage)
                return ModelResponse(
                    value=_parse_json(text),
                    raw_text=text,
                    usage=accumulated_usage,
                    latency_seconds=time.monotonic() - started,
                    attempts=attempt,
                )
            except Exception as exc:
                last_error = exc
                if attempt <= self.config.max_retries:
                    time.sleep(min(2 ** (attempt - 1), 8))
        assert last_error is not None
        raise ModelRequestError(
            f"model request failed after {self.config.max_retries + 1} attempts: "
            f"{type(last_error).__name__}: {last_error}",
            attempts=self.config.max_retries + 1,
            usage=accumulated_usage,
            raw_text=last_text,
            finish_reason=last_finish_reason,
        ) from last_error

    def _build_request_kwargs(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if self.config.seed is not None and not self._openai_style:
            kwargs["seed"] = self.config.seed

        if self._openai_style:
            # GPT-5.x chat completions prefer max_completion_tokens.
            kwargs["max_completion_tokens"] = max_tokens
            effort = self.config.reasoning_effort
            if effort and effort not in {"disabled", "none"}:
                kwargs["reasoning_effort"] = effort
            # Many reasoning models reject custom temperature.
        else:
            kwargs["temperature"] = self.config.temperature
            kwargs["max_tokens"] = max_tokens
            kwargs["extra_body"] = {"thinking": {"type": self.config.thinking_mode}}
            if self.config.thinking_mode == "enabled":
                kwargs["reasoning_effort"] = self.config.reasoning_effort
        return kwargs

    def _usage_from_response(self, response: Any) -> Usage:
        prompt_tokens = int(response.usage.prompt_tokens if response.usage else 0)
        completion_tokens = int(response.usage.completion_tokens if response.usage else 0)
        completion_details = (
            response.usage.completion_tokens_details if response.usage else None
        )
        prompt_details = response.usage.prompt_tokens_details if response.usage else None
        reasoning_tokens = int(
            (completion_details.reasoning_tokens if completion_details else 0) or 0
        )
        cached_prompt_tokens = int((prompt_details.cached_tokens if prompt_details else 0) or 0)
        return Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
            total_tokens=int(response.usage.total_tokens if response.usage else 0),
            estimated_cost_usd=self._estimate_cost(
                prompt_tokens,
                cached_prompt_tokens,
                completion_tokens,
            ),
        )

    def _estimate_cost(
        self,
        prompt_tokens: int,
        cached_prompt_tokens: int,
        completion_tokens: int,
    ) -> float | None:
        input_rate = self.config.input_cost_per_million
        cached_input_rate = self.config.cached_input_cost_per_million
        output_rate = self.config.output_cost_per_million
        if input_rate is None or output_rate is None:
            return None
        uncached_prompt_tokens = max(prompt_tokens - cached_prompt_tokens, 0)
        input_cost = uncached_prompt_tokens * input_rate
        if cached_prompt_tokens:
            input_cost += cached_prompt_tokens * (
                cached_input_rate if cached_input_rate is not None else input_rate
            )
        return (input_cost + completion_tokens * output_rate) / 1_000_000


# Backward-compatible alias used by older imports/tests.
DeepSeekClient = OpenAICompatClient
