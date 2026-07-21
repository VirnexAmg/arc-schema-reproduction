from __future__ import annotations

import json
from dataclasses import replace

from arc_schema.agents import HarnessAgent
from arc_schema.config import ExperimentConfig
from arc_schema.core import Usage
from arc_schema.deepseek_client import ModelResponse
from arc_schema.history import AppendOnlyJournal
from arc_schema.mock import ToyEnvironment, toy_observation
from arc_schema.runner import run_agent


class ScriptedClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls = 0

    def complete_json(self, messages: list[dict], purpose: str) -> ModelResponse:
        del messages, purpose
        value = self.responses[self.calls]
        self.calls += 1
        return ModelResponse(
            value=value,
            raw_text=json.dumps(value),
            usage=Usage(),
            latency_seconds=0.0,
            attempts=1,
        )


def config(max_actions: int = 3, explore_steps: int = 0) -> ExperimentConfig:
    base = ExperimentConfig(
        game_id="toy",
        max_environment_actions=max_actions,
        harness_model_attempts=1,
        explore_steps=explore_steps,
        max_plan_steps=3,
        run_timeout_seconds=60.0,
        max_model_calls_per_run=20,
    )
    return replace(base, planner_max_nodes=20)


def test_backtest_failure_retreats_to_explore(tmp_path) -> None:
    invalid_for_current = {
        "states": [{"id": "other", "snapshot_ref": "missing", "goal": True}],
        "transitions": [],
    }
    client = ScriptedClient([invalid_for_current])
    environment = ToyEnvironment()
    metrics = run_agent(
        HarnessAgent(client, config(max_actions=1, explore_steps=0)),
        environment,
        config(max_actions=1, explore_steps=0),
        run_index=0,
        seed=0,
        journal_path=tmp_path / "gate.jsonl",
    )
    assert metrics.backtest_failures == 1
    assert metrics.environment_actions == 1
    assert metrics.exploration_actions == 1
    assert environment.actions == 1


def test_prediction_mismatch_discards_remaining_plan_then_explores(tmp_path) -> None:
    s0 = toy_observation(0)
    wrong_prediction = {
        "states": [
            {"id": "s0", "snapshot_ref": f"obs_{s0.fingerprint}"},
            {
                "id": "wrong",
                "base_ref": f"obs_{s0.fingerprint}",
                "snapshot_patch": {
                    "rows": [{"y": 0, "rle": "9:1,0:2"}],
                    "metadata": {"state": "NOT_FINISHED", "levels_completed": 0},
                },
            },
            {
                "id": "goal",
                "base_ref": f"obs_{s0.fingerprint}",
                "snapshot_patch": {
                    "rows": [{"y": 0, "rle": "2:1,0:2"}],
                    "metadata": {
                        "state": "WIN",
                        "levels_completed": 1,
                        "available_actions": [1, 2],
                    },
                },
                "goal": True,
            },
        ],
        "transitions": [
            {"from": "s0", "action": {"id": 1}, "to": "wrong"},
            {"from": "wrong", "action": {"id": 1}, "to": "goal"},
        ],
    }
    s1 = toy_observation(1)
    corrected = {
        "states": [
            {"id": "s0", "snapshot_ref": f"obs_{s1.fingerprint}"},
            {
                "id": "s1",
                "base_ref": f"obs_{s1.fingerprint}",
                "snapshot_patch": {
                    "rows": [{"y": 0, "rle": "2:1,0:2"}],
                    "metadata": {
                        "state": "WIN",
                        "levels_completed": 1,
                        "available_actions": [1, 2],
                    },
                },
                "goal": True,
            },
        ],
        "transitions": [
            {"from": "s0", "action": {"id": 1}, "to": "s1"},
        ],
    }
    client = ScriptedClient([wrong_prediction, corrected])
    environment = ToyEnvironment()
    path = tmp_path / "mismatch.jsonl"
    metrics = run_agent(
        HarnessAgent(client, config(max_actions=3, explore_steps=0)),
        environment,
        config(max_actions=3, explore_steps=0),
        run_index=0,
        seed=0,
        journal_path=path,
    )
    assert metrics.prediction_mismatches == 1
    assert metrics.environment_actions >= 2
    assert metrics.exploration_actions >= 1
    assert client.calls >= 1
    events = [item["event"] for item in AppendOnlyJournal.read_records(path)]
    assert "prediction_mismatch" in events
    # After a mismatch the harness explores instead of aborting; that explore may
    # finish the toy episode before a second world-model call is required.
    assert metrics.status in {"win", "action_budget_exhausted"} or metrics.completed


def test_explore_first_skips_world_model(tmp_path) -> None:
    client = ScriptedClient([])
    environment = ToyEnvironment()
    metrics = run_agent(
        HarnessAgent(client, config(max_actions=2, explore_steps=2)),
        environment,
        config(max_actions=2, explore_steps=2),
        run_index=0,
        seed=0,
        journal_path=tmp_path / "explore.jsonl",
    )
    assert client.calls == 0
    assert metrics.exploration_actions == 2
    assert metrics.environment_actions == 2
    assert environment.position == 2
    assert metrics.completed
