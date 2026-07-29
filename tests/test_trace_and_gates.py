from __future__ import annotations

from arc_schema.core import Action, RunMetrics, Transition
from arc_schema.deliberation import DeliberationSession
from arc_schema.history import AppendOnlyJournal
from arc_schema.mock import DeterministicMockClient, ToyEnvironment, toy_observation
from arc_schema.program_world_model import DEFAULT_WORLD_MODEL_STUB
from arc_schema.workspace import Workspace


def test_workspace_versions_notes_and_wm(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    assert (tmp_path / "ws" / "wm_versions").exists()
    assert list((tmp_path / "ws" / "wm_versions").glob("v*.py"))
    version = ws.write_notes("# Working notes\n## Hypotheses\n- H1: rotate\n")
    assert version == 1
    assert list((tmp_path / "ws" / "notes_history").glob("v*.md"))
    assert "rotate" in ws.read_notes()


def test_vacuous_backtest_does_not_certify(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    ws.write_code(DEFAULT_WORLD_MODEL_STUB)
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=2,
        planner_max_nodes=10,
        max_plan_steps=2,
        max_model_calls=10,
    )
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    current = toy_observation(0)
    result = session._dispatch_tool("run_backtest", {}, current, [], metrics, journal)
    assert result["ok"] is True
    assert result["certified"] is False
    assert "vacuous" in str(result.get("warning", "")).lower()
    assert ws.certified is False


def test_mismatch_blocks_planned_until_recertify(tmp_path) -> None:
    env = ToyEnvironment()
    before = env.current
    after = env.step(Action(id=1))
    history = [Transition(before, Action(id=1), after)]
    ws = Workspace(tmp_path / "ws")
    # Correct toy model that fits the one transition.
    source = """\
def step(state, action):
    nxt = state.copy()
    if int(action["id"]) == 1:
        pos = int(nxt.frame[0][0])
        pos = min(2, pos + 1)
        nxt.frame[0][0] = pos
        if pos == 2:
            nxt.state = "WIN"
            nxt.levels_completed = 1
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed >= 1
"""
    ws.write_code(source)
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=3,
        max_model_calls=10,
    )
    bt = session._dispatch_tool("run_backtest", {}, after, history, metrics, journal)
    assert bt["certified"] is True
    ws.record_mismatch({"reason": "predicted state differs from real observation"})
    assert ws.mismatch_blocks_planning is True
    commit, obs = session._handle_commit(
        {"kind": "planned", "actions": [{"id": 1, "data": {}}]},
        after,
        history,
    )
    assert commit is None
    assert "blocked" in str(obs.get("error", "")).lower()
    # Re-certify without new edits should clear the block.
    bt2 = session._dispatch_tool("run_backtest", {}, after, history, metrics, journal)
    assert bt2["certified"] is True
    assert ws.mismatch_blocks_planning is False
    commit2, obs2 = session._handle_commit(
        {"kind": "planned", "actions": [{"id": 1, "data": {}}]},
        after,
        history,
    )
    assert commit2 is not None
    assert obs2["ok"] is True
