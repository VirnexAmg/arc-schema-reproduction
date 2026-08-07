from __future__ import annotations

"""
Schema harness 集成测试：用 Toy + 模拟模型验证主闭环（无网络）。

优先阅读这三个测试（对应 Codex 学习方案第二阶段）：
1. test_compound_schema_cycle_solves_toy_in_two_model_calls
   → 两次 schema_cycle：探索 → 改 WM/认证/BFS/planned → Toy WIN
2. test_schema_executes_monitored_navigation_without_bfs_plan
   → 无 BFS 时可用 certified navigation 完成关卡
3. test_navigation_stops_immediately_on_prediction_mismatch
   → navigation burst 在第一步预测失配时立即截断
"""

import json
from dataclasses import replace

from arc_schema.agents import SchemaHarnessAgent, make_harness_agent
from arc_schema.config import ExperimentConfig
from arc_schema.core import Usage
from arc_schema.deepseek_client import ModelResponse
from arc_schema.history import AppendOnlyJournal
from arc_schema.c05_validation import run_c05
from arc_schema.mock import (
    CompoundDeterministicMockClient,
    DeterministicMockClient,
    TOY_STEP_SOURCE,
    ToyEnvironment,
)
from arc_schema.runner import run_agent
from arc_schema.workspace import Workspace


class HypothesisExperimentClient:
    def __init__(self) -> None:
        self.phase = 0

    def complete_json(self, messages, purpose):
        assert purpose == "deliberation"
        if self.phase == 0:
            value = {
                "tool": "update_hypotheses",
                "args": {
                    "hypotheses": [
                        {
                            "id": "H_changes",
                            "statement": "ACTION2 changes the frame.",
                            "status": "active",
                        },
                        {
                            "id": "H_fixed",
                            "statement": "ACTION2 leaves the frame fixed.",
                            "status": "active",
                        },
                    ],
                    "reason": "register alternatives",
                    "evidence_seq": [],
                },
            }
        elif self.phase == 1:
            value = {
                "tool": "propose_experiment",
                "args": {
                    "action": {"id": 2},
                    "hypotheses": [
                        {"id": "H_changes", "prediction": "frame changes"},
                        {"id": "H_fixed", "prediction": "frame stays fixed"},
                    ],
                    "rationale": "one-step discriminator",
                    "evidence_seq": [],
                },
            }
        else:
            observation = json.loads(str(messages[-1]["content"]))
            value = {
                "tool": "commit_actions",
                "args": {
                    "kind": "exploration",
                    "experiment_id": observation["experiment_id"],
                    "actions": [{"id": 2}],
                    "rationale": "execute registered discriminator",
                    "evidence_seq": [],
                },
            }
        self.phase += 1
        return ModelResponse(
            value=value,
            raw_text=json.dumps(value),
            usage=Usage(),
            latency_seconds=0.0,
            attempts=1,
        )


class NavigationClient:
    def __init__(self, source: str = TOY_STEP_SOURCE) -> None:
        self.phase = 0
        self.source = source

    def complete_json(self, messages, purpose):
        del messages
        assert purpose == "deliberation"
        if self.phase == 0:
            value = {"tool": "write_code", "args": {"source": self.source}}
        elif self.phase == 1:
            value = {"tool": "run_backtest", "args": {}}
        else:
            value = {
                "tool": "commit_actions",
                "args": {
                    "kind": "navigation",
                    "actions": [{"id": 2}, {"id": 1}],
                    "rationale": "use a safe staging action, then advance to the goal",
                    "evidence_seq": [1],
                },
            }
        self.phase += 1
        return ModelResponse(
            value=value,
            raw_text=json.dumps(value),
            usage=Usage(),
            latency_seconds=0.0,
            attempts=1,
        )


class TerminalMismatchClient(NavigationClient):
    def __init__(self, source: str) -> None:
        super().__init__(source)
        self.rollover_reasons: list[str] = []
        self.context_events: list[dict] = []

    def request_session_rollover(self, reason: str) -> None:
        self.rollover_reasons.append(reason)

    def checkpoint_context(self, reason: str, metadata=None):
        payload = {"reason": reason, "metadata": dict(metadata or {})}
        self.context_events.append(payload)
        return payload

    def drain_context_events(self):
        events = list(self.context_events)
        self.context_events.clear()
        return events


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
    assert metrics.bfs_plans_generated == 1
    assert metrics.bfs_derived_planned_actions == metrics.planned_actions
    assert metrics.prequential_predictions == 1
    assert metrics.prequential_matches == 1
    assert metrics.prequential_mismatches == 0
    workspace_root = tmp_path / "workspace-harness-0"
    assert (workspace_root / "world_model.py").exists()
    assert (workspace_root / "trace_index.md").exists()
    assert (workspace_root / "wm_versions").exists()
    assert list((workspace_root / "wm_versions").glob("v*.py"))
    assert list((workspace_root / "notes_history").glob("v*.md"))
    trace_index = (workspace_root / "trace_index.md").read_text(encoding="utf-8")
    assert "Backtests and BFS plans" in trace_index
    assert "Prequential predictions" in trace_index
    workspace = Workspace(workspace_root)
    assert "def step" in workspace.read_code()
    assert "Hypotheses" in workspace.read_notes()


def test_compound_schema_cycle_solves_toy_in_two_model_calls(tmp_path) -> None:
    """Toy 闭环金标：2 次模型调用完成 explore→认证→BFS planned→WIN。"""
    config = ExperimentConfig(
        agent_runtime="codex_cli",
        game_id="toy",
        max_environment_actions=3,
        harness_mode="schema",
        deliberation_max_turns=2,
        max_plan_steps=4,
        planner_max_nodes=100,
        explore_steps=0,
        explore_burst=1,
        wm_time_reserve_seconds=0.0,
        max_model_calls_per_run=4,
        run_timeout_seconds=60.0,
        schema_commit_only=True,
        target_levels_completed=1,
        auto_reset_on_game_over=False,
    )
    client = CompoundDeterministicMockClient()
    metrics = run_agent(
        SchemaHarnessAgent(client, config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "compound.jsonl",
    )
    assert metrics.completed
    assert metrics.model_calls == 2
    assert metrics.exploration_actions == 1
    assert metrics.planned_actions == 1
    assert metrics.bfs_plans_generated == 1
    assert metrics.prequential_matches == 1
    assert metrics.hypothesis_revisions == 2
    ledger = Workspace(tmp_path / "workspace-harness-0").read_hypothesis_ledger()
    assert ledger["hypotheses"]["H_action1_progress"]["status"] == "supported"


def test_c05_offline_contract_covers_full_toy_loop(tmp_path) -> None:
    report = run_c05(
        ExperimentConfig(max_model_calls_per_run=2),
        tmp_path / "c05",
        CompoundDeterministicMockClient(),
        require_codex_trace=False,
    )
    assert report["status"] == "passed"
    assert all(report["checks"].values())
    assert report["metrics"]["model_calls"] == 2
    assert report["checks"]["within_configured_model_call_cap"] is True
    assert (tmp_path / "c05" / "c05-report.json").exists()


def test_schema_model_call_budget_stops_without_blind_action_padding(tmp_path) -> None:
    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=10,
        harness_mode="schema",
        deliberation_max_turns=8,
        max_plan_steps=3,
        planner_max_nodes=50,
        explore_steps=0,
        explore_burst=3,
        wm_time_reserve_seconds=0.0,
        max_model_calls_per_run=1,
        run_timeout_seconds=60.0,
        auto_reset_on_game_over=False,
    )
    path = tmp_path / "model-budget.jsonl"
    metrics = run_agent(
        SchemaHarnessAgent(DeterministicMockClient(), config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=path,
    )
    assert metrics.status == "model_call_budget"
    assert metrics.model_calls == 1
    assert metrics.model_budget_exhausted_at_action == 0
    assert metrics.environment_actions == 0
    events = [record["event"] for record in AppendOnlyJournal.read_records(path)]
    assert "model_call_budget" in events
    assert "forced_explore" not in events


def test_schema_records_registered_experiment_outcome(tmp_path) -> None:
    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=1,
        harness_mode="schema",
        deliberation_max_turns=8,
        max_plan_steps=3,
        planner_max_nodes=50,
        explore_steps=0,
        explore_burst=1,
        wm_time_reserve_seconds=0.0,
        max_model_calls_per_run=10,
        run_timeout_seconds=60.0,
        auto_reset_on_game_over=False,
    )
    path = tmp_path / "experiment-outcome.jsonl"
    agent = SchemaHarnessAgent(HypothesisExperimentClient(), config)
    metrics = run_agent(
        agent,
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=path,
    )
    assert metrics.environment_actions == 1
    assert metrics.discriminating_experiments == 1
    assert metrics.experiments_observed == 1
    ledger = agent.workspace.read_hypothesis_ledger()
    experiment = next(iter(ledger["experiments"].values()))
    assert experiment["status"] == "observed"
    assert "outcome" in experiment
    events = [record["event"] for record in AppendOnlyJournal.read_records(path)]
    assert "experiment_observed" in events
    assert "hypothesis_ledger_revision" in events


def test_schema_executes_monitored_navigation_without_bfs_plan(tmp_path) -> None:
    """已认证但无 BFS plan 时，monitored navigation 可合法多步推进并过关。"""
    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=3,
        harness_mode="schema",
        deliberation_max_turns=6,
        max_plan_steps=4,
        planner_max_nodes=50,
        explore_steps=1,
        explore_burst=1,
        wm_time_reserve_seconds=0.0,
        max_model_calls_per_run=10,
        run_timeout_seconds=60.0,
        auto_reset_on_game_over=False,
    )
    path = tmp_path / "navigation.jsonl"
    metrics = run_agent(
        SchemaHarnessAgent(NavigationClient(), config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=path,
    )
    assert metrics.completed
    assert metrics.levels_completed == 1
    assert metrics.exploration_actions == 1
    assert metrics.navigation_actions == 2
    assert metrics.planned_actions == 0
    assert metrics.bfs_plans_generated == 0
    assert metrics.prequential_predictions == 2
    assert metrics.prequential_matches == 2
    assert metrics.max_deliberation_context_chars > 0
    records = AppendOnlyJournal.read_records(path)
    started = [record for record in records if record["event"] == "commit_execution_started"]
    assert started[-1]["payload"]["kind"] == "navigation"


def test_navigation_stops_immediately_on_prediction_mismatch(tmp_path) -> None:
    """navigation 安全带：第一步 prequential mismatch 后剩余 burst 立即停止。"""
    mismatching_source = """\
def step(state, action):
    nxt = state.copy()
    aid = int(action["id"])
    if aid == 1:
        nxt.frame[0][0] = min(2, int(nxt.frame[0][0]) + 1)
        if int(nxt.frame[0][0]) == 2:
            nxt.state = "WIN"
            nxt.levels_completed = 1
    elif aid == 2:
        nxt.frame[0][0] = 0
    return nxt

def is_goal(state):
    return state.state == "WIN"
"""
    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=2,
        harness_mode="schema",
        deliberation_max_turns=6,
        max_plan_steps=4,
        planner_max_nodes=50,
        explore_steps=1,
        explore_burst=1,
        wm_time_reserve_seconds=0.0,
        max_model_calls_per_run=10,
        run_timeout_seconds=60.0,
        auto_reset_on_game_over=False,
    )
    metrics = run_agent(
        SchemaHarnessAgent(NavigationClient(mismatching_source), config),
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=tmp_path / "navigation-mismatch.jsonl",
    )
    assert metrics.completed is False
    assert metrics.environment_actions == 2
    assert metrics.navigation_actions == 1
    assert metrics.prequential_mismatches == 1
    assert metrics.prediction_mismatches == 1


def test_level_boundary_is_recorded_even_when_winning_prediction_mismatches(
    tmp_path,
) -> None:
    row_fill_source = """\
def step(state, action):
    nxt = state.copy()
    if int(action["id"]) == 1:
        for x, value in enumerate(nxt.frame[0]):
            if int(value) == 0:
                nxt.frame[0][x] = 1
                break
        if all(int(value) == 1 for value in nxt.frame[0]):
            nxt.state = "WIN"
            nxt.levels_completed = 1
    return nxt

def is_goal(state):
    return state.state == "WIN"
"""
    config = ExperimentConfig(
        game_id="toy",
        max_environment_actions=3,
        harness_mode="schema",
        deliberation_max_turns=6,
        max_plan_steps=4,
        planner_max_nodes=50,
        explore_steps=1,
        explore_burst=1,
        wm_time_reserve_seconds=0.0,
        max_model_calls_per_run=10,
        run_timeout_seconds=60.0,
        target_levels_completed=1,
        auto_reset_on_game_over=False,
    )
    path = tmp_path / "winning-mismatch.jsonl"
    client = TerminalMismatchClient(row_fill_source)
    agent = SchemaHarnessAgent(client, config)
    metrics = run_agent(
        agent,
        ToyEnvironment(),
        config,
        run_index=0,
        seed=0,
        journal_path=path,
    )

    assert metrics.completed
    assert metrics.prequential_mismatches == 1
    events = [record["event"] for record in AppendOnlyJournal.read_records(path)]
    assert events.index("prediction_mismatch") < events.index("level_boundary")
    assert client.rollover_reasons == []
    assert metrics.codex_context_checkpoints == 1
    assert metrics.codex_context_checkpoint_reasons == {"level_boundary": 1}
    assert agent.workspace.mismatch_blocks_planning
    assert agent.workspace.planning_block_reason == "level_boundary"
