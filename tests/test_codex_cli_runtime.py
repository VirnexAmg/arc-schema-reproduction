from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

from arc_schema.codex_cli_client import CodexCliClient
import arc_schema.cli as cli_module
from arc_schema.cli import _configured
from arc_schema.config import ExperimentConfig, ModelConfig
from arc_schema.core import Usage, usage_budget_reason
from arc_schema.deepseek_client import ModelRequestError, ModelResponse
from arc_schema.agents import SchemaHarnessAgent
from arc_schema.history import AppendOnlyJournal
from arc_schema.mock import ToyEnvironment
from arc_schema.runner import run_agent
from arc_schema.workspace import Workspace


VALID_MODEL = """\
def step(state, action):
    return state.copy()

def is_goal(state):
    return False
"""


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        agent_runtime="codex_cli",
        codex_executable="codex-test",
        model=ModelConfig(
            model="gpt-5.6-sol",
            reasoning_effort="xhigh",
            input_cost_per_million=5.0,
            cached_input_cost_per_million=0.5,
            output_cost_per_million=30.0,
        ),
    )


def test_cli_notional_cost_flag_overrides_dotenv_config(monkeypatch) -> None:
    base = replace(_config(), max_notional_cost_usd=15.0)
    monkeypatch.setattr(
        ExperimentConfig,
        "from_env",
        classmethod(lambda cls: base),
    )
    args = Namespace(
        runs=None,
        max_actions=None,
        output=None,
        explore_steps=None,
        run_timeout=None,
        max_spend=None,
        experiment_max_spend=None,
        request_spend_reserve=None,
        max_model_calls=None,
        max_notional_cost=30.0,
    )

    assert _configured(args).max_notional_cost_usd == 30.0


def test_preregistered_process_can_override_dotenv_caps(monkeypatch) -> None:
    monkeypatch.setenv("ARC_DOTENV_OVERRIDE", "false")
    monkeypatch.setenv("ARC_TARGET_LEVELS_COMPLETED", "7")
    monkeypatch.setenv("ARC_MAX_MODEL_CALLS_PER_RUN", "72")
    monkeypatch.setenv("ARC_MAX_TOTAL_TOKENS_PER_RUN", "14000000")
    monkeypatch.setenv("ARC_BASELINE_MAX_BATCH_ACTIONS", "16")

    config = ExperimentConfig.from_env()

    assert config.target_levels_completed == 7
    assert config.max_model_calls_per_run == 72
    assert config.max_total_tokens_per_run == 14_000_000
    assert config.baseline_max_batch_actions == 16


def test_full_run_target_passes_codex_mainline_preflight(monkeypatch) -> None:
    base = _config()
    config = replace(
        base,
        target_levels_completed=7,
        schema_commit_only=True,
        max_environment_actions=800,
        max_model_calls_per_run=72,
        max_total_tokens_per_run=14_000_000,
        max_uncached_tokens_per_run=4_500_000,
        max_output_tokens_per_run=1_200_000,
        token_reserve_per_call=600_000,
        max_notional_cost_usd=75.0,
        model=replace(base.model, vision_enabled=True),
    )
    monkeypatch.setattr(cli_module, "_configured", lambda args: config)
    monkeypatch.setattr(cli_module, "_codex_executable_available", lambda value: True)
    monkeypatch.setattr(
        cli_module,
        "run_experiment",
        lambda *args, **kwargs: Path("full-run-preflight.json"),
    )

    result = cli_module._real_ab(Namespace(agents="harness", confirm_api_cost_risk=True))

    assert result == 0


def test_batched_baseline_full_run_passes_codex_mainline_preflight(
    monkeypatch,
) -> None:
    base = _config()
    config = replace(
        base,
        target_levels_completed=7,
        schema_commit_only=True,
        baseline_max_batch_actions=16,
        max_environment_actions=800,
        max_model_calls_per_run=72,
        max_total_tokens_per_run=14_000_000,
        max_uncached_tokens_per_run=4_500_000,
        max_output_tokens_per_run=1_200_000,
        token_reserve_per_call=600_000,
        max_notional_cost_usd=75.0,
        model=replace(base.model, vision_enabled=True),
    )
    monkeypatch.setattr(cli_module, "_configured", lambda args: config)
    monkeypatch.setattr(cli_module, "_codex_executable_available", lambda value: True)
    monkeypatch.setattr(
        cli_module,
        "run_experiment",
        lambda *args, **kwargs: Path("batched-baseline-preflight.json"),
    )

    result = cli_module._real_ab(Namespace(agents="baseline", confirm_api_cost_risk=True))

    assert result == 0


def test_codex_cli_starts_then_resumes_one_thread(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    call_kwargs: list[dict[str, object]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        call_kwargs.append(dict(kwargs))
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text(
            '{"tool":"commit_actions","args":{"kind":"exploration",'
            '"actions":[{"id":1,"data":{}}]}}',
            encoding="utf-8",
        )
        stdout = (
            json.dumps({"type": "thread.started", "thread_id": "thread-test"})
            + "\n"
            + json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "reasoning", "text": "先检查证据。"},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 4,
                        "output_tokens": 3,
                        "reasoning_output_tokens": 2,
                    },
                }
            )
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    client = CodexCliClient(_config(), run_process=fake_run)
    workspace = Workspace(tmp_path / "workspace")
    client.bind_workspace(workspace)
    messages = [{"role": "user", "content": "Return one action JSON."}]

    first = client.complete_json(messages, "deliberation")
    second = client.complete_json(messages, "deliberation")

    assert first.value["tool"] == "commit_actions"
    assert first.usage.total_tokens == 13
    assert first.usage.reasoning_tokens == 2
    assert abs((first.usage.notional_cost_usd or 0.0) - 0.000122) < 1e-12
    assert first.reasoning_text == "先检查证据。"
    assert call_kwargs[0]["encoding"] == "utf-8"
    assert call_kwargs[0]["errors"] == "replace"
    assert "schema_cycle or done" in str(call_kwargs[0]["input"])
    assert "Do not launch PowerShell" in str(call_kwargs[0]["input"])
    assert "--model" in calls[0]
    assert 'model_reasoning_effort="xhigh"' in calls[0]
    assert "features.remote_plugin=false" in calls[0]
    assert "features.remote_plugin=false" in calls[1]
    resume_index = calls[1].index("resume")
    assert calls[1][resume_index : resume_index + 2] == ["resume", "thread-test"]
    assert second.value == first.value
    assert (workspace.root / "codex-cli-events.jsonl").exists()


def test_codex_cli_attaches_latest_png_on_start_and_resume(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    png = b"\x89PNG\r\n\x1a\nmodel-visible-frame"

    def fake_run(argv, **kwargs):
        del kwargs
        calls.append(list(argv))
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text('{"tool":"done","args":{"reason":"ok"}}', encoding="utf-8")
        stdout = (
            '{"type":"thread.started","thread_id":"vision-thread"}\n'
            '{"type":"turn.completed","usage":{"input_tokens":10,'
            '"output_tokens":2}}'
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    client = CodexCliClient(_config(), run_process=fake_run)
    workspace = Workspace(tmp_path / "workspace")
    client.bind_workspace(workspace)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Inspect the attached frame."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")
                    },
                },
            ],
        }
    ]

    client.complete_json(messages, "deliberation")
    client.complete_json(messages, "deliberation")

    for argv in calls:
        image_index = argv.index("--image")
        image_path = Path(argv[image_index + 1])
        assert image_path.read_bytes() == png
        assert image_path.parent == workspace.root / "vision-inputs"


def test_codex_direct_action_baseline_has_no_schema_or_write_access(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    prompts: list[str] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        prompts.append(str(kwargs["input"]))
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text('{"action":{"id":1,"data":{}}}', encoding="utf-8")
        stdout = (
            '{"type":"thread.started","thread_id":"baseline-thread"}\n'
            '{"type":"turn.completed","usage":{"input_tokens":10,'
            '"output_tokens":2}}'
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    client = CodexCliClient(
        _config(),
        run_process=fake_run,
        runtime_role="direct_action_baseline",
    )
    runtime_root = tmp_path / "baseline-runtime"
    client.bind_workspace_path(runtime_root)
    response = client.complete_json(
        [{"role": "user", "content": "Choose one action."}],
        "baseline_action",
    )

    assert response.value == {"action": {"id": 1, "data": {}}}
    assert "strict no-harness condition" in prompts[0]
    assert "schema_cycle" not in prompts[0]
    sandbox_index = calls[0].index("--sandbox")
    assert calls[0][sandbox_index + 1] == "read-only"
    assert client.workspace_native is False


def test_codex_batched_direct_baseline_has_strict_batch_protocol(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    prompts: list[str] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        prompts.append(str(kwargs["input"]))
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text(
            '{"actions":[{"id":1,"data":{}},{"id":2,"data":{}}]}',
            encoding="utf-8",
        )
        stdout = (
            '{"type":"thread.started","thread_id":"batch-thread"}\n'
            '{"type":"turn.completed","usage":{"input_tokens":10,'
            '"output_tokens":2}}'
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    config = replace(_config(), baseline_max_batch_actions=16)
    client = CodexCliClient(
        config,
        run_process=fake_run,
        runtime_role="direct_action_baseline",
    )
    client.bind_workspace_path(tmp_path / "batched-baseline-runtime")
    response = client.complete_json(
        [{"role": "user", "content": "Choose a batch."}],
        "baseline_action",
    )

    assert len(response.value["actions"]) == 2
    assert "1 to 16" in prompts[0]
    assert "Never submit RESET action 0" in prompts[0]
    assert "executable world" in prompts[0]
    assert "schema_cycle" not in prompts[0]
    sandbox_index = calls[0].index("--sandbox")
    assert calls[0][sandbox_index + 1] == "read-only"


def test_codex_cli_streams_utf8_events_and_captures_thread_early(tmp_path: Path) -> None:
    client = CodexCliClient(_config())
    trace = tmp_path / "events.jsonl"
    script = (
        'print(\'{"type":"thread.started","thread_id":"stream-test"}\');'
        'print(\'{"type":"item.completed","item":{"type":'
        '"agent_message","text":"中文事件"}}\')'
    )
    completed = client._run_streaming_process(
        [sys.executable, "-c", script],
        prompt="",
        cwd=tmp_path,
        trace_path=trace,
    )
    assert completed.returncode == 0
    assert client.thread_id == "stream-test"
    assert "中文事件" in trace.read_text(encoding="utf-8")


def test_codex_cli_recovers_after_completed_turn_process_hangs(tmp_path: Path) -> None:
    config = replace(
        _config(),
        codex_cli_timeout_seconds=3.0,
        codex_post_turn_exit_grace_seconds=0.05,
    )
    client = CodexCliClient(config)
    trace = tmp_path / "events.jsonl"
    script = (
        "import json,time;"
        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message',"
        '\'text\':\'{"tool":"done","args":{"reason":"ok"}}\'}}),flush=True);'
        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,"
        "'output_tokens':2}}),flush=True);"
        "time.sleep(30)"
    )

    started = time.monotonic()
    completed = client._run_streaming_process(
        [sys.executable, "-c", script],
        prompt="",
        cwd=tmp_path,
        trace_path=trace,
    )

    assert time.monotonic() - started < 2.0
    assert completed.returncode == 0
    events = client._parse_events(completed.stdout)
    stats = client._event_stats(events)
    assert stats["post_completion_forced_exits"] == 1
    assert "harness.post_completion_forced_exit" in trace.read_text(encoding="utf-8")


def test_shell_tool_use_forces_context_rollover(tmp_path: Path) -> None:
    def fake_run(argv, **kwargs):
        del kwargs
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text('{"tool":"done","args":{"reason":"ok"}}', encoding="utf-8")
        stdout = "\n".join(
            [
                '{"type":"thread.started","thread_id":"thread-shell"}',
                '{"type":"item.completed","item":{"type":"command_execution",'
                '"status":"completed","command":"Get-ChildItem"}}',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":1}}',
            ]
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    client = CodexCliClient(_config(), run_process=fake_run)
    client.bind_workspace(Workspace(tmp_path / "workspace"))
    client.complete_json([{"role": "user", "content": "done"}], "deliberation")

    assert client.last_event_stats["command_executions"] == 1
    assert client.rollover_pending
    assert client.rollover_reason == "shell_tool_context"


def test_codex_session_rollover_happens_between_deliberations(tmp_path: Path) -> None:
    config = replace(
        _config(),
        codex_context_policy="fixed_turns",
        codex_max_turns_per_thread=1,
    )

    def fake_run(argv, **kwargs):
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text('{"tool":"done","args":{"reason":"ok"}}', encoding="utf-8")
        stdout = (
            '{"type":"thread.started","thread_id":"thread-roll"}\n'
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":1}}'
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    client = CodexCliClient(config, run_process=fake_run)
    client.bind_workspace(Workspace(tmp_path / "workspace"))
    client.complete_json([{"role": "user", "content": "done"}], "deliberation")
    assert client.rollover_pending
    rollover = client.begin_deliberation()
    assert rollover is not None
    assert rollover["previous_thread_prefix"] == "thread-r"
    assert rollover["reason"] == "fixed_turn_limit"
    assert rollover["turns_in_previous_thread"] == 1
    assert client.thread_id is None


def test_persistent_context_policy_ignores_turn_and_prompt_watermarks(tmp_path: Path) -> None:
    config = replace(
        _config(),
        codex_context_policy="persistent",
        codex_max_turns_per_thread=1,
        codex_soft_context_prompt_tokens=1,
        codex_hard_context_prompt_tokens=2,
    )

    def fake_run(argv, **kwargs):
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text('{"tool":"done","args":{"reason":"ok"}}', encoding="utf-8")
        stdout = (
            '{"type":"thread.started","thread_id":"thread-persistent"}\n'
            '{"type":"turn.completed","usage":{"input_tokens":500000,"output_tokens":1}}'
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    client = CodexCliClient(config, run_process=fake_run)
    client.bind_workspace(Workspace(tmp_path / "workspace"))
    client.complete_json([{"role": "user", "content": "done"}], "deliberation")

    assert not client.rollover_pending
    assert client.drain_context_events() == []


def test_adaptive_policy_checkpoints_soft_then_rolls_at_hard_watermark(
    tmp_path: Path,
) -> None:
    config = replace(
        _config(),
        codex_context_policy="adaptive",
        codex_soft_context_prompt_tokens=100,
        codex_hard_context_prompt_tokens=200,
    )
    calls = 0

    def fake_run(argv, **kwargs):
        nonlocal calls
        calls += 1
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text('{"tool":"done","args":{"reason":"ok"}}', encoding="utf-8")
        input_tokens = 150 if calls == 1 else 250
        stdout = (
            '{"type":"thread.started","thread_id":"thread-adaptive"}\n'
            f'{{"type":"turn.completed","usage":{{"input_tokens":{input_tokens},'
            '"cached_input_tokens":50,"output_tokens":1}}'
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    workspace = Workspace(tmp_path / "workspace")
    client = CodexCliClient(config, run_process=fake_run)
    client.bind_workspace(workspace)
    messages = [{"role": "user", "content": "done"}]

    client.complete_json(messages, "deliberation")
    assert not (workspace.root / "context_checkpoints").exists()
    accepted_source = workspace.read_code()
    workspace.world_model_path.write_text("def broken(:\n", encoding="utf-8")
    rejected = workspace.sync_external_changes()
    assert rejected["code_error"]
    soft_events = client.drain_context_events()
    assert [event["reason"] for event in soft_events] == ["prompt_soft_watermark"]
    assert not client.rollover_pending
    soft_manifest = Path(soft_events[0]["manifest_path"])
    assert soft_manifest.exists()
    manifest = json.loads(soft_manifest.read_text(encoding="utf-8"))
    assert {item["name"] for item in manifest["snapshot_files"]} == {
        "world_model.py",
        "notes.md",
        "hypotheses.json",
    }
    assert (soft_manifest.parent / "world_model.py").read_text(encoding="utf-8") == accepted_source

    client.complete_json(messages, "deliberation")
    hard_events = client.drain_context_events()
    assert [event["reason"] for event in hard_events] == ["prompt_hard_watermark"]
    assert client.rollover_pending
    assert client.rollover_reason == "prompt_hard_watermark"
    rollover = client.begin_deliberation()
    assert rollover is not None
    assert rollover["configured_prompt_limit"] == 200


def test_codex_event_stats_classify_transport_failure() -> None:
    events = [
        {"type": "error", "message": "Reconnecting... 2/5 (request timed out)"},
        {
            "type": "item.completed",
            "item": {
                "type": "error",
                "message": "Falling back from WebSockets to HTTPS transport.",
            },
        },
        {"type": "error", "message": "request timed out"},
        {"type": "turn.failed", "error": {"message": "request timed out"}},
    ]
    stats = CodexCliClient._event_stats(events)
    assert stats["transport_reconnects"] == 1
    assert stats["https_fallbacks"] == 1
    assert stats["transport_timeouts"] == 1
    assert stats["turn_failures"] == 1


def test_workspace_versions_valid_native_edits_and_restores_invalid_ones(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    start_wm_version = workspace.version
    workspace.world_model_path.write_text(VALID_MODEL, encoding="utf-8")
    workspace.notes_path.write_text("# Revised evidence\n", encoding="utf-8")

    accepted = workspace.sync_external_changes()

    assert accepted["code_changed"]
    assert accepted["notes_changed"]
    assert workspace.version == start_wm_version + 1
    assert workspace.notes_version == 1
    accepted_source = workspace.read_code()

    workspace.world_model_path.write_text("def broken(:\n", encoding="utf-8")
    rejected = workspace.sync_external_changes()

    assert "code_error" in rejected
    assert workspace.read_code() == accepted_source
    assert workspace.version == start_wm_version + 1


def test_codex_runtime_does_not_require_api_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = replace(_config(), codex_executable="codex")
    client = CodexCliClient(config)
    assert client.thread_id is None


def test_subscription_resource_caps_are_independent() -> None:
    usage = Usage(
        prompt_tokens=900,
        cached_prompt_tokens=300,
        completion_tokens=80,
        total_tokens=980,
        notional_cost_usd=1.25,
    )
    assert (
        usage_budget_reason(usage, max_total_tokens=1500, total_token_reserve=600) == "token_budget"
    )
    assert usage_budget_reason(usage, max_uncached_tokens=600) == "uncached_token_budget"
    assert usage_budget_reason(usage, max_output_tokens=80) == "output_token_budget"
    assert usage_budget_reason(usage, max_notional_cost_usd=1.0) == "notional_cost_budget"


class _DoneClient:
    def complete_json(self, messages, purpose):
        del messages, purpose
        return ModelResponse(
            value={"tool": "done", "args": {"reason": "need more thought"}},
            raw_text='{"tool":"done","args":{"reason":"need more thought"}}',
            usage=Usage(total_tokens=5),
            latency_seconds=0.0,
            attempts=1,
        )


class _InfrastructureFailureClient:
    workspace_native = True

    def __init__(self) -> None:
        self.calls = 0
        self.last_event_stats = {}
        self.last_failure_kind = None

    def bind_workspace(self, workspace) -> None:
        del workspace

    def complete_json(self, messages, purpose):
        del messages, purpose
        self.calls += 1
        self.last_event_stats = {
            "transport_reconnects": 9,
            "https_fallbacks": 1,
            "transport_timeouts": 1,
            "turn_failures": 1,
            "tool_failures": 0,
            "post_completion_forced_exits": 2,
        }
        self.last_failure_kind = "infrastructure_error"
        raise ModelRequestError(
            "codex turn failed: request timed out",
            attempts=1,
            usage=Usage(),
        )


def test_transport_failure_is_recorded_and_fails_fast(tmp_path: Path) -> None:
    client = _InfrastructureFailureClient()
    config = ExperimentConfig(
        agent_runtime="codex_cli",
        game_id="toy",
        max_environment_actions=4,
        max_model_calls_per_run=4,
        deliberation_max_turns=2,
        schema_commit_only=True,
        run_timeout_seconds=60,
        wm_time_reserve_seconds=0,
    )
    journal_path = tmp_path / "infrastructure.jsonl"
    metrics = run_agent(
        SchemaHarnessAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=journal_path,
    )
    assert client.calls == 1
    assert metrics.status == "infrastructure_error"
    assert metrics.model_calls == 1
    assert metrics.codex_transport_reconnects == 9
    assert metrics.codex_https_fallbacks == 1
    assert metrics.codex_transport_timeouts == 1
    assert metrics.codex_turn_failures == 1
    assert metrics.codex_post_completion_forced_exits == 2
    records = list(AppendOnlyJournal.read_records(journal_path))
    assert any(item["event"] == "infrastructure_error" for item in records)


def test_commit_only_mode_never_pads_run_with_blind_actions(tmp_path: Path) -> None:
    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=5,
        max_model_calls_per_run=2,
        deliberation_max_turns=1,
        explore_steps=5,
        schema_commit_only=True,
        run_timeout_seconds=60,
        wm_time_reserve_seconds=0,
    )
    metrics = run_agent(
        SchemaHarnessAgent(_DoneClient(), config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "run.jsonl",
    )
    assert metrics.environment_actions == 0
    assert metrics.model_calls == 2
    assert metrics.status == "model_call_budget"
