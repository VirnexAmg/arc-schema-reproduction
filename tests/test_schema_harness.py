from __future__ import annotations

from dataclasses import replace

from arc_schema.agents import SchemaHarnessAgent, make_harness_agent
from arc_schema.config import ExperimentConfig
from arc_schema.mock import DeterministicMockClient, ToyEnvironment
from arc_schema.runner import run_agent
from arc_schema.workspace import Workspace


def test_make_harness_defaults_to_schema() -> None:
    agent = make_harness_agent(DeterministicMockClient(), ExperimentConfig())
    assert isinstance(agent, SchemaHarnessAgent)


def test_schema_harness_solves_toy_via_program_wm(tmp_path) -> None:
    config = replace(
        ExperimentConfig(
            game_id="toy",
            max_environment_actions=3,
            harness_mode="schema",
            deliberation_max_turns=8,
            max_plan_steps=3,
            planner_max_nodes=50,
            explore_steps=0,
            explore_burst=1,
            wm_time_reserve_seconds=0.0,
            max_model_calls_per_run=20,
            run_timeout_seconds=60.0,
            auto_reset_on_game_over=False,
        )
    )
    client = DeterministicMockClient()
    agent = SchemaHarnessAgent(client, config)
    metrics = run_agent(
        agent,
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "schema.jsonl",
    )
    assert metrics.completed
    assert metrics.levels_completed == 1
    assert metrics.exploration_actions == 1
    assert metrics.planned_actions == 1
    workspace_root = tmp_path / "workspace-harness-0"
    assert (workspace_root / "world_model.py").exists()
    assert (workspace_root / "trace_index.md").exists()
    assert (workspace_root / "wm_versions").exists()
    assert list((workspace_root / "wm_versions").glob("v*.py"))
    assert list((workspace_root / "notes_history").glob("v*.md"))
    workspace = Workspace(workspace_root)
    assert "def step" in workspace.read_code()
    assert "Hypotheses" in workspace.read_notes()
