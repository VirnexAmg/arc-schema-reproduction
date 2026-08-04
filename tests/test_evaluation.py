from __future__ import annotations

import json
from dataclasses import replace

from arc_schema.config import ExperimentConfig, ModelConfig
from arc_schema.core import Usage
from arc_schema.deepseek_client import ModelRequestError, ModelResponse
from arc_schema.evaluation import pair_validity, run_experiment
from arc_schema.history import AppendOnlyJournal
from arc_schema.mock import DeterministicMockClient, ToyEnvironment


def test_mock_ab_runs_end_to_end_and_saves_machine_readable_results(tmp_path) -> None:
    config = ExperimentConfig(
        game_id="toy",
        runs=2,
        max_environment_actions=2,
        seeds=(7, 11),
        output_dir=tmp_path,
        explore_steps=0,
        harness_mode="schema",
        deliberation_max_turns=8,
        wm_time_reserve_seconds=0.0,
        max_plan_steps=3,
        planner_max_nodes=50,
    )
    result_path = run_experiment(
        config,
        environment_factory=lambda seed: ToyEnvironment(),
        client_factory=DeterministicMockClient,
    )
    document = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(document["results"]) == 4
    assert {row["agent"] for row in document["results"]} == {"baseline", "harness"}
    assert "navigation_actions" in document["aggregate"]["harness"]
    assert "bfs_no_plan_results" in document["aggregate"]["harness"]
    assert "max_deliberation_context_chars" in document["aggregate"]["harness"]
    assert all(row["completed"] for row in document["results"])
    assert all(row["paired_valid"] for row in document["results"])
    assert document["aggregate"]["baseline"]["completion_rate"] == 1.0
    assert document["aggregate"]["harness"]["completion_rate"] == 1.0
    assert document["aggregate"]["comparison"]["paired_valid_runs"] == 2

    for journal_path in result_path.parent.glob("*.jsonl"):
        records = list(AppendOnlyJournal.read_records(journal_path))
        AppendOnlyJournal.verify(records)
        assert records[-1]["event"] == "run_finished"


def test_pair_validity_rejects_failed_side() -> None:
    baseline = {
        "agent": "baseline",
        "status": "failed",
        "environment_actions": 0,
        "error": "boom",
    }
    harness = {
        "agent": "harness",
        "status": "action_budget_exhausted",
        "environment_actions": 8,
        "error": None,
    }
    valid, reason = pair_validity(baseline, harness, max_environment_actions=8)
    assert valid is False
    assert reason == "baseline_failed"


def test_pair_validity_accepts_shared_budget_exhaustion() -> None:
    baseline = {
        "agent": "baseline",
        "status": "action_budget_exhausted",
        "environment_actions": 8,
        "error": None,
    }
    harness = {
        "agent": "harness",
        "status": "action_budget_exhausted",
        "environment_actions": 8,
        "error": None,
    }
    valid, reason = pair_validity(baseline, harness, max_environment_actions=8)
    assert valid is True
    assert reason is None


def test_pair_validity_accepts_success_against_model_call_budget() -> None:
    baseline = {
        "agent": "baseline",
        "status": "model_call_budget",
        "environment_actions": 18,
        "error": None,
    }
    harness = {
        "agent": "harness",
        "status": "target_levels_reached",
        "environment_actions": 71,
        "error": None,
    }
    valid, reason = pair_validity(
        baseline,
        harness,
        max_environment_actions=160,
    )
    assert valid is True
    assert reason is None


def test_baseline_stops_at_model_call_budget_without_fallback(tmp_path) -> None:
    from arc_schema.agents import BaselineAgent
    from arc_schema.runner import run_agent

    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=3,
        max_model_calls_per_run=1,
    )
    client = DeterministicMockClient()
    metrics = run_agent(
        BaselineAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "baseline-call-budget.jsonl",
    )
    assert metrics.status == "model_call_budget"
    assert metrics.model_calls == 1
    assert metrics.environment_actions == 1
    assert metrics.fallback_actions == 0


class BatchedBaselineClient:
    def __init__(self, actions: list[int] | None = None, *, malformed: bool = False) -> None:
        self.actions = actions or [1, 1, 1]
        self.malformed = malformed
        self.calls = 0
        self.last_messages = None

    def complete_json(self, messages, purpose: str) -> ModelResponse:
        self.last_messages = messages
        assert purpose == "baseline_action"
        self.calls += 1
        value = (
            {"action": {"id": 1, "data": {}}}
            if self.malformed
            else {"actions": [{"id": action, "data": {}} for action in self.actions]}
        )
        return ModelResponse(
            value=value,
            raw_text=json.dumps(value),
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            latency_seconds=0.0,
            attempts=1,
        )


def test_batched_baseline_executes_one_call_until_level_boundary(tmp_path) -> None:
    from arc_schema.agents import BaselineAgent
    from arc_schema.runner import run_agent

    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=20,
        max_model_calls_per_run=5,
        baseline_max_batch_actions=16,
        target_levels_completed=1,
        model=ModelConfig(vision_enabled=True),
    )
    client = BatchedBaselineClient([1, 1, 1])
    journal_path = tmp_path / "batched-level.jsonl"
    metrics = run_agent(
        BaselineAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=journal_path,
    )

    assert metrics.status == "target_levels_reached"
    assert metrics.levels_completed == 1
    assert metrics.model_calls == 1
    assert metrics.environment_actions == 2
    assert metrics.baseline_batches == 1
    assert metrics.baseline_actions_proposed == 3
    assert metrics.baseline_batches_truncated == 1
    assert isinstance(client.last_messages[1]["content"], list)
    assert '"batch_constraints"' in client.last_messages[1]["content"][0]["text"]
    records = list(AppendOnlyJournal.read_records(journal_path))
    finished = next(row for row in records if row["event"] == "baseline_batch_finished")
    assert finished["payload"]["stop_reason"] == "level_boundary"
    assert finished["payload"]["executed_actions"] == 2


def test_batched_baseline_respects_environment_action_cap(tmp_path) -> None:
    from arc_schema.agents import BaselineAgent
    from arc_schema.runner import run_agent

    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=2,
        max_model_calls_per_run=5,
        baseline_max_batch_actions=16,
    )
    client = BatchedBaselineClient([2, 2])
    metrics = run_agent(
        BaselineAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "batched-action-cap.jsonl",
    )

    assert metrics.status == "action_budget_exhausted"
    assert metrics.model_calls == 1
    assert metrics.environment_actions == 2


def test_batched_baseline_protocol_error_is_fail_fast(tmp_path) -> None:
    from arc_schema.agents import BaselineAgent
    from arc_schema.runner import run_agent

    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=5,
        baseline_max_batch_actions=16,
    )
    client = BatchedBaselineClient(malformed=True)
    metrics = run_agent(
        BaselineAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "batched-protocol.jsonl",
    )

    assert metrics.status == "failed"
    assert metrics.model_calls == 1
    assert metrics.environment_actions == 0
    assert metrics.fallback_actions == 0
    assert "top-level 'actions' key" in (metrics.error or "")


def test_pair_validity_rejects_timeout() -> None:
    baseline = {
        "agent": "baseline",
        "status": "action_budget_exhausted",
        "environment_actions": 50,
        "error": None,
    }
    harness = {
        "agent": "harness",
        "status": "timeout",
        "environment_actions": 17,
        "error": None,
    }
    valid, reason = pair_validity(baseline, harness, max_environment_actions=50)
    assert valid is False
    assert reason == "harness_timeout"


class FailingThenOkClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, messages, purpose: str) -> ModelResponse:
        del messages, purpose
        self.calls += 1
        if self.calls == 1:
            raise ModelRequestError("simulated failure", attempts=1, usage=Usage())
        return ModelResponse(
            value={"action": {"id": 1, "data": {}}},
            raw_text='{"action":{"id":1,"data":{}}}',
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            latency_seconds=0.0,
            attempts=1,
        )


def test_baseline_falls_back_on_model_failure(tmp_path) -> None:
    from arc_schema.agents import BaselineAgent
    from arc_schema.runner import run_agent

    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=2,
        explore_steps=0,
        model=ModelConfig(max_retries=0),
    )
    client = FailingThenOkClient()
    metrics = run_agent(
        BaselineAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "fallback.jsonl",
    )
    assert metrics.fallback_actions >= 1
    assert metrics.environment_actions == 2
    assert metrics.status != "failed"


def test_hard_timeout_stops_run(tmp_path) -> None:
    from arc_schema.agents import BaselineAgent
    from arc_schema.runner import run_agent

    class SlowClient:
        def complete_json(self, messages, purpose: str) -> ModelResponse:
            del messages, purpose
            import time

            time.sleep(0.05)
            return ModelResponse(
                value={"action": {"id": 1, "data": {}}},
                raw_text='{"action":{"id":1,"data":{}}}',
                usage=Usage(),
                latency_seconds=0.05,
                attempts=1,
            )

    config = replace(
        ExperimentConfig(
            game_id="toy",
            max_environment_actions=10,
            run_timeout_seconds=0.01,
        )
    )
    metrics = run_agent(
        BaselineAgent(SlowClient(), config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "timeout.jsonl",
    )
    assert metrics.status == "timeout"
    assert metrics.environment_actions < 10


def test_baseline_respects_request_reserve_before_api_call(tmp_path) -> None:
    from arc_schema.agents import BaselineAgent
    from arc_schema.runner import run_agent

    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=2,
        max_spend_usd=0.5,
        request_spend_reserve_usd=0.75,
    )
    client = FailingThenOkClient()
    metrics = run_agent(
        BaselineAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "spend.jsonl",
    )
    assert metrics.status == "spend_budget"
    assert metrics.environment_actions == 0
    assert client.calls == 0
