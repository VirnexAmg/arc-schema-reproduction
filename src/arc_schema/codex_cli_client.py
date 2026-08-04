from __future__ import annotations

"""
持久 Codex CLI 适配器：Schema 主线 runtime。

整局 ARC run 复用同一 CLI 线程。Codex 可在 workspace 内查看帧、编辑
world_model.py / notes.md；最终消息仍须是小型 JSON 指令，环境动作继续走
与 API 实现相同的可审计提交门。

阅读导引：
- CodexCliClient：拉起/恢复线程，解析最终 JSON（schema_cycle|done 或 baseline action）
- CODEX_SCHEMA_INSTRUCTIONS：harness 侧系统指令
- 线程 rollover：按 turn 数或 prompt tokens 换新线程，避免上下文无限膨胀
- usage / notional：从 Codex 事件流解析 token，按配置单价算资源代理
"""

import base64
import binascii
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from arc_schema.config import ExperimentConfig
from arc_schema.core import Usage
from arc_schema.deepseek_client import ModelRequestError, ModelResponse, parse_json_object


CODEX_SCHEMA_INSTRUCTIONS = """You are the persistent coding agent for one
Schema-style ARC-AGI-3 run. Work directly in the run workspace. Inspect
world_model.py, notes.md, hypotheses.json, the journal, and current PNG when
useful. Build an executable, revisable theory that helps complete as many levels
as possible; it may be instrumentally useful without being the designer's unique
true mechanism. Never read game source or hard-code a supplied puzzle answer.

You may edit world_model.py and notes.md directly. The complete current snapshot,
recent transitions, model, notes, ledger, and frame are already in the request.
Do not launch PowerShell, cmd, bash, terminal commands, subprocesses, or recursive
workspace enumeration. Use native apply_patch/file tools; if those are unavailable,
use schema_cycle.workspace_edits. The harness validates and versions edits. Do not
directly edit hypotheses.json or the journal.
Every real environment action must be explicitly submitted through the JSON
command protocol described in the turn. Return exactly one JSON object as your
final message. In this workspace-native runtime, the final JSON must be
schema_cycle or done; never end with the compatibility write_code, apply_patch,
or write_notes JSON tools. If native file editing is unavailable, put the patch
and notes inside schema_cycle.workspace_edits so certification can still happen
atomically. Prefer evidence-gathering over theory-only loops when uncertain.
When schema_cycle is offered, prefer it as the closeout for one agentic episode:
inspect and edit the workspace first, then request automatic full-history replay,
exact BFS when available, or a monitored navigation/exploration fallback in the
same final JSON. Include a concise decision_record; do not reveal hidden chain of
thought.
"""


CODEX_DIRECT_ACTION_BASELINE_INSTRUCTIONS = """You are the persistent direct-action
control baseline for one ARC-AGI-3 run. Use only the current observation, the
supplied recent transition history, the visible frame context, and conversation
memory from your own earlier action choices. Infer action meanings only from
observed transitions.

This is a strict no-harness condition. Do not create or use an executable world
model, replay/backtest, BFS/search procedure, certification gate, notes file,
hypothesis ledger, workspace memory, or multi-action plan. Do not inspect local
files, the repository, game source, network resources, or use shell/tool calls.
Choose exactly one currently legal real-environment action. Your final message
must be exactly one JSON object with this schema and no other keys or prose:
{"action":{"id":1,"data":{}}}
"""


def _direct_action_baseline_instructions(config: ExperimentConfig) -> str:
    max_batch = config.baseline_max_batch_actions
    if max_batch == 1:
        return CODEX_DIRECT_ACTION_BASELINE_INSTRUCTIONS
    return f"""You are the persistent batched direct-action control baseline for one
ARC-AGI-3 run. Use only the current observation, supplied recent transition
history, visible frame context, and conversation memory from your own earlier
action choices. Infer action meanings only from observed transitions.

This is a strict no-harness condition. Do not create or use an executable world
model, replay/backtest, BFS/search procedure, certification gate, notes file,
hypothesis ledger, workspace memory, or other external persistent artifact. Do
not inspect local files, the repository, game source, network resources, or use
shell/tool calls. You may reason about and return a short coherent open-loop
sequence, but it will be executed without observation feedback and may be cut
short at a level or terminal boundary. Return 1 to {max_batch} currently legal
real-environment actions; prefer one action when new visual feedback is needed.
Never submit RESET action 0. Your final message must be exactly one JSON object
with this schema and no other keys or prose:
{{"actions":[{{"id":1,"data":{{}}}}]}}
"""


RunProcess = Callable[..., subprocess.CompletedProcess[str]]


class CodexCliClient:
    """基于持久 ``codex exec`` 会话的 ModelClient；schema 或 direct baseline 角色。"""

    workspace_native = True

    def __init__(
        self,
        config: ExperimentConfig,
        *,
        run_process: RunProcess = subprocess.run,
        runtime_role: str = "schema",
    ) -> None:
        if config.agent_runtime != "codex_cli":
            raise ValueError("CodexCliClient requires ARC_AGENT_RUNTIME=codex_cli")
        if not config.codex_executable:
            raise ValueError("ARC_CODEX_EXECUTABLE must not be empty")
        if runtime_role not in {"schema", "direct_action_baseline"}:
            raise ValueError("runtime_role must be schema or direct_action_baseline")
        self.config = config
        self.runtime_role = runtime_role
        self.workspace_native = runtime_role == "schema"
        self._run_process = run_process
        self._stream_real_process = run_process is subprocess.run
        self._workspace: Path | None = None
        self.thread_id: str | None = None
        self.turns_in_thread = 0
        self.rollover_pending = False
        self.session_generation = 0
        self.last_rollover: dict[str, Any] | None = None
        self.rollover_reason = "turn_or_prompt_budget"
        self.last_event_stats: dict[str, int] = {}
        self.last_failure_kind: str | None = None

    def bind_workspace(self, workspace: Any) -> None:
        self._workspace = Path(workspace.root).resolve()

    def bind_workspace_path(self, root: Path) -> None:
        """Bind an isolated runtime/trace directory without a harness Workspace."""
        self._workspace = Path(root).resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)

    def begin_deliberation(self) -> dict[str, Any] | None:
        """Apply a deferred rollover only between deliberation episodes."""
        self.last_rollover = None
        if not self.rollover_pending or self.thread_id is None:
            return None
        previous_prefix = self.thread_id[:8]
        self.thread_id = None
        self.turns_in_thread = 0
        self.rollover_pending = False
        self.session_generation += 1
        self.last_rollover = {
            "previous_thread_prefix": previous_prefix,
            "session_generation": self.session_generation,
            "reason": self.rollover_reason,
        }
        self.rollover_reason = "turn_or_prompt_budget"
        return dict(self.last_rollover)

    def request_session_rollover(self, reason: str) -> None:
        if self.thread_id is not None:
            self.rollover_pending = True
            self.rollover_reason = str(reason)[:200] or "external_request"

    def command(
        self,
        output_path: Path,
        image_paths: tuple[Path, ...] = (),
    ) -> list[str]:
        """Build argv separately so it can be preflighted without consuming quota."""
        common = [
            self.config.codex_executable,
            "exec",
            "-c",
            "features.remote_plugin=false",
        ]
        image_args = [item for image_path in image_paths for item in ("--image", str(image_path))]
        if self.thread_id is None:
            return [
                *common,
                "--json",
                "--model",
                self.config.model.model,
                "-c",
                f'model_reasoning_effort="{self.config.model.reasoning_effort}"',
                *image_args,
                "--sandbox",
                ("workspace-write" if self.runtime_role == "schema" else "read-only"),
                "--skip-git-repo-check",
                "-C",
                str(self._require_workspace()),
                "--output-last-message",
                str(output_path),
                "-",
            ]
        # ``exec resume`` accepts --output-last-message; keep the session's model,
        # reasoning and sandbox settings rather than creating a fresh agent.
        return [
            *common,
            "resume",
            self.thread_id,
            *image_args,
            "-",
            "--json",
            "--output-last-message",
            str(output_path),
        ]

    def complete_json(
        self,
        messages: list[dict[str, Any]],
        purpose: str,
    ) -> ModelResponse:
        del purpose
        self.last_event_stats = {}
        self.last_failure_kind = None
        workspace = self._require_workspace()
        user_content = self._latest_user_text(messages)
        image_paths = self._materialize_latest_images(messages)
        runtime_instructions = (
            CODEX_SCHEMA_INSTRUCTIONS
            if self.runtime_role == "schema"
            else _direct_action_baseline_instructions(self.config)
        )
        prompt = (
            f"{runtime_instructions}\n\n{self._first_system_text(messages)}\n\n{user_content}"
            if self.thread_id is None
            else user_content
        )
        started = time.monotonic()
        with tempfile.NamedTemporaryFile(
            prefix="codex-last-",
            suffix=".txt",
            dir=workspace,
            delete=False,
        ) as handle:
            output_path = Path(handle.name)
        try:
            trace_path = workspace / "codex-cli-events.jsonl"
            if self._stream_real_process:
                completed = self._run_streaming_process(
                    self.command(output_path, image_paths),
                    prompt=prompt,
                    cwd=workspace,
                    trace_path=trace_path,
                )
                already_traced = True
            else:
                completed = self._run_process(
                    self.command(output_path, image_paths),
                    input=prompt,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=self.config.codex_cli_timeout_seconds,
                    check=False,
                    cwd=workspace,
                )
                already_traced = False
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            if not already_traced:
                self._append_trace(trace_path, stdout)
            events = self._parse_events(stdout)
            self._capture_thread_id(events)
            self.last_event_stats = self._event_stats(events)
            if (
                self.runtime_role == "direct_action_baseline"
                and self.last_event_stats.get("command_executions", 0) > 0
            ):
                self.last_failure_kind = "protocol_error"
                raise ModelRequestError(
                    "direct-action baseline protocol violation: local command used",
                    attempts=1,
                    usage=self._usage_from_events(events),
                )
            raw_text = (
                output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
            )
            usage = self._usage_from_events(events)
            if completed.returncode != 0:
                if (
                    self.last_event_stats.get("turn_failures", 0) > 0
                    or self.last_event_stats.get("transport_timeouts", 0) > 0
                ):
                    self.last_failure_kind = "infrastructure_error"
                detail = (stderr or stdout)[-2000:]
                raise ModelRequestError(
                    f"codex exec exited {completed.returncode}: {detail}",
                    attempts=1,
                    usage=usage,
                    raw_text=raw_text,
                )
            if not raw_text:
                raw_text = self._last_agent_text(events)
            reasoning_text = self._reasoning_from_events(events)
            try:
                value = parse_json_object(raw_text)
            except Exception as exc:
                raise ModelRequestError(
                    f"codex final message was not a JSON tool command: {exc}",
                    attempts=1,
                    usage=usage,
                    raw_text=raw_text,
                ) from exc
            response = ModelResponse(
                value=value,
                raw_text=raw_text,
                usage=usage,
                latency_seconds=time.monotonic() - started,
                attempts=1,
                reasoning_text=reasoning_text,
                reasoning_status=(
                    "present"
                    if reasoning_text
                    else ("tokens_only" if usage.reasoning_tokens else "absent")
                ),
            )
            self.turns_in_thread += 1
            max_turns = max(1, self.config.codex_max_turns_per_thread)
            prompt_limit = max(0, self.config.codex_rollover_prompt_tokens)
            if self.turns_in_thread >= max_turns or (
                prompt_limit > 0 and usage.prompt_tokens >= prompt_limit
            ):
                self.rollover_pending = True
            if self.last_event_stats.get("command_executions", 0) > 0:
                # Shell output is persistent Codex-thread context and was the main
                # source of 500k+ token turns in the C1 trace.  The prompt forbids
                # shell use, but roll over defensively if a turn still used it.
                self.rollover_pending = True
                self.rollover_reason = "shell_tool_context"
            return response
        except subprocess.TimeoutExpired as exc:
            partial_stdout = exc.output if isinstance(exc.output, str) else ""
            partial_events = self._parse_events(partial_stdout)
            self._capture_thread_id(partial_events)
            self.last_event_stats = self._event_stats(partial_events)
            self.last_failure_kind = "infrastructure_error"
            raise ModelRequestError(
                f"codex exec timed out after {self.config.codex_cli_timeout_seconds}s",
                attempts=1,
                usage=self._usage_from_events(partial_events),
            ) from exc
        finally:
            output_path.unlink(missing_ok=True)

    @staticmethod
    def _append_trace(path: Path, stdout: str) -> None:
        with path.open("a", encoding="utf-8") as trace:
            trace.write(stdout)
            if stdout and not stdout.endswith("\n"):
                trace.write("\n")

    def _run_streaming_process(
        self,
        argv: list[str],
        *,
        prompt: str,
        cwd: Path,
        trace_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Run Codex with live JSONL persistence so partial turns remain auditable."""
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            bufsize=1,
            start_new_session=os.name != "nt",
            env={
                **os.environ,
                # Codex emits JSONL as UTF-8.  Making the child contract explicit
                # also prevents Windows' active code page from corrupting native
                # trace text before we can persist it.
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        )
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        turn_completed = threading.Event()

        def _read_stdout() -> None:
            assert process.stdout is not None
            with trace_path.open("a", encoding="utf-8") as trace:
                for line in process.stdout:
                    stdout_parts.append(line)
                    trace.write(line)
                    trace.flush()
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict):
                        self._capture_thread_id([event])
                        if event.get("type") == "turn.completed":
                            turn_completed.set()

        def _read_stderr() -> None:
            assert process.stderr is not None
            for chunk in process.stderr:
                stderr_parts.append(chunk)

        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()
        deadline = time.monotonic() + self.config.codex_cli_timeout_seconds
        recovered_completed_turn = False
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(
                        argv,
                        self.config.codex_cli_timeout_seconds,
                    )
                if turn_completed.is_set():
                    grace = min(
                        max(0.0, self.config.codex_post_turn_exit_grace_seconds),
                        remaining,
                    )
                    try:
                        returncode = process.wait(timeout=grace)
                    except subprocess.TimeoutExpired:
                        # A terminal model event is authoritative.  Codex can remain
                        # alive because a tool child inherited its pipes; clean up
                        # only this invocation's process tree and keep the response.
                        self._terminate_process_tree(process)
                        returncode = 0
                        recovered_completed_turn = True
                    break
                try:
                    returncode = process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except subprocess.TimeoutExpired as exc:
            self._terminate_process_tree(process)
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            raise subprocess.TimeoutExpired(
                argv,
                self.config.codex_cli_timeout_seconds,
                output="".join(stdout_parts),
                stderr="".join(stderr_parts),
            ) from exc
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        if recovered_completed_turn:
            recovery_event = (
                json.dumps(
                    {
                        "type": "harness.post_completion_forced_exit",
                        "grace_seconds": self.config.codex_post_turn_exit_grace_seconds,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
            stdout_parts.append(recovery_event)
            self._append_trace(trace_path, recovery_event)
        return subprocess.CompletedProcess(
            argv,
            returncode,
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
        )

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        """Terminate only the Codex invocation and descendants, then reap it."""
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    # A completed turn is already authoritative. Do not let a
                    # sluggish Windows process-tree helper consume the model
                    # timeout or defeat the post-completion recovery bound.
                    timeout=1,
                    check=False,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)

    def _require_workspace(self) -> Path:
        if self._workspace is None:
            raise ValueError("CodexCliClient must be bound to a run workspace")
        return self._workspace

    @staticmethod
    def _latest_user_text(messages: list[dict[str, Any]]) -> str:
        for item in reversed(messages):
            if item.get("role") != "user":
                continue
            content = item.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                if texts:
                    return "\n".join(texts)
        raise ValueError("messages contain no user content")

    def _materialize_latest_images(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[Path, ...]:
        """Decode latest-turn data-URL images and attach them to ``codex exec``.

        Codex CLI receives raster inputs through ``--image`` rather than through
        stdin. Keeping content-addressed copies in the run workspace also makes
        the exact model-visible frames auditable after the experiment.
        """
        image_urls: list[str] = []
        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                break
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "image_url":
                    continue
                image = part.get("image_url")
                if isinstance(image, dict) and isinstance(image.get("url"), str):
                    image_urls.append(str(image["url"]))
            break

        if not image_urls:
            return ()

        image_dir = self._require_workspace() / "vision-inputs"
        image_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for image_url in image_urls:
            if not image_url.startswith("data:image/") or "," not in image_url:
                raise ValueError("Codex CLI vision input must be an image data URL")
            header, encoded = image_url.split(",", 1)
            if not header.endswith(";base64"):
                raise ValueError("Codex CLI vision input must use base64 encoding")
            subtype = header.removeprefix("data:image/").removesuffix(";base64")
            extension = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}.get(
                subtype.lower()
            )
            if extension is None:
                raise ValueError(f"unsupported Codex CLI image type: {subtype}")
            try:
                payload = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("invalid base64 Codex CLI vision input") from exc
            if not payload or len(payload) > 25 * 1024 * 1024:
                raise ValueError("Codex CLI vision input has invalid size")
            digest = hashlib.sha256(payload).hexdigest()
            image_path = image_dir / f"{digest}.{extension}"
            if not image_path.exists():
                image_path.write_bytes(payload)
            paths.append(image_path)
        return tuple(paths)

    @staticmethod
    def _first_system_text(messages: list[dict[str, Any]]) -> str:
        for item in messages:
            if item.get("role") == "system" and isinstance(item.get("content"), str):
                return str(item["content"])
        return ""

    @staticmethod
    def _parse_events(stdout: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
        return events

    def _capture_thread_id(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            if event.get("type") == "thread.started":
                value = event.get("thread_id")
                if isinstance(value, str) and value:
                    self.thread_id = value
                    return

    @staticmethod
    def _event_stats(events: list[dict[str, Any]]) -> dict[str, int]:
        reconnects = 0
        https_fallbacks = 0
        transport_timeouts = 0
        turn_failures = 0
        tool_failures = 0
        command_executions = 0
        post_completion_forced_exits = 0
        for event in events:
            message = str(event.get("message", ""))
            if event.get("type") == "error" and "reconnecting" in message.lower():
                reconnects += 1
            if event.get("type") == "error" and message.strip().lower() == "request timed out":
                transport_timeouts += 1
            if event.get("type") == "turn.failed":
                turn_failures += 1
            if event.get("type") == "harness.post_completion_forced_exit":
                post_completion_forced_exits += 1
            item = event.get("item")
            if isinstance(item, dict):
                item_message = str(item.get("message", ""))
                if "falling back" in item_message.lower():
                    https_fallbacks += 1
            if (
                isinstance(item, dict)
                and item.get("type") in {"command_execution", "mcp_tool_call"}
                and item.get("status") == "failed"
            ):
                tool_failures += 1
            if isinstance(item, dict) and item.get("type") == "command_execution":
                command_executions += 1
        return {
            "transport_reconnects": reconnects,
            "https_fallbacks": https_fallbacks,
            "transport_timeouts": transport_timeouts,
            "turn_failures": turn_failures,
            "tool_failures": tool_failures,
            "command_executions": command_executions,
            "post_completion_forced_exits": post_completion_forced_exits,
            "event_count": len(events),
        }

    @staticmethod
    def _last_agent_text(events: list[dict[str, Any]]) -> str:
        for event in reversed(events):
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"agent_message", "assistant_message"}:
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    return text
        return ""

    @staticmethod
    def _reasoning_from_events(events: list[dict[str, Any]]) -> str | None:
        summaries: list[str] = []
        for event in events:
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") != "reasoning":
                continue
            value = item.get("text") or item.get("content") or item.get("summary")
            if isinstance(value, str) and value.strip():
                summaries.append(value.strip())
            elif isinstance(value, list):
                for part in value:
                    if isinstance(part, dict):
                        text = part.get("text") or part.get("summary_text")
                        if isinstance(text, str) and text.strip():
                            summaries.append(text.strip())
        return "\n\n".join(summaries) or None

    def _usage_from_events(self, events: list[dict[str, Any]]) -> Usage:
        """Accept both current turn.completed usage and older nested layouts."""
        for event in reversed(events):
            candidates = [event.get("usage")]
            result = event.get("result")
            if isinstance(result, dict):
                candidates.append(result.get("usage"))
            for value in candidates:
                if not isinstance(value, dict):
                    continue
                prompt = int(value.get("input_tokens", value.get("prompt_tokens", 0)) or 0)
                completion = int(value.get("output_tokens", value.get("completion_tokens", 0)) or 0)
                cached = int(
                    value.get("cached_input_tokens", value.get("cached_prompt_tokens", 0)) or 0
                )
                reasoning = int(
                    value.get(
                        "reasoning_output_tokens",
                        value.get("reasoning_tokens", 0),
                    )
                    or 0
                )
                total = int(value.get("total_tokens", prompt + completion) or 0)
                uncached = max(prompt - cached, 0)
                input_rate = self.config.model.input_cost_per_million
                cached_rate = self.config.model.cached_input_cost_per_million
                output_rate = self.config.model.output_cost_per_million
                notional = None
                if input_rate is not None and output_rate is not None:
                    notional = (
                        uncached * input_rate
                        + cached * (cached_rate if cached_rate is not None else input_rate)
                        + completion * output_rate
                    ) / 1_000_000
                return Usage(
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    reasoning_tokens=reasoning,
                    cached_prompt_tokens=cached,
                    total_tokens=total,
                    notional_cost_usd=notional,
                )
        return Usage()
