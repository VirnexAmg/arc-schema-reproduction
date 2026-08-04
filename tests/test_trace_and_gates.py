from __future__ import annotations

import json

from arc_schema.core import Action, Observation, RunMetrics, Transition
from arc_schema.deliberation import DeliberationSession
from arc_schema.history import AppendOnlyJournal
from arc_schema.mock import DeterministicMockClient, ToyEnvironment, toy_observation
from arc_schema.program_world_model import DEFAULT_WORLD_MODEL_STUB
from arc_schema.workspace import Workspace


def test_workspace_versions_notes_and_wm(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    assert (tmp_path / "ws" / "wm_versions").exists()
    assert (tmp_path / "ws" / "hypotheses.json").exists()
    assert (tmp_path / "ws" / "hypothesis_versions").exists()
    assert list((tmp_path / "ws" / "wm_versions").glob("v*.py"))
    version = ws.write_notes("# Working notes\n## Hypotheses\n- H1: rotate\n")
    assert version == 1
    assert list((tmp_path / "ws" / "notes_history").glob("v*.md"))
    assert "rotate" in ws.read_notes()


def test_confirmed_hypothesis_status_is_normalized_and_audited(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=3,
        max_model_calls=10,
    )
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)

    result = session._dispatch_tool(
        "update_hypotheses",
        {
            "hypotheses": [
                {
                    "id": "H_confirmed",
                    "statement": "The observation supports this mechanism.",
                    "status": "confirmed",
                }
            ],
            "reason": "record the supported interpretation",
            "evidence_seq": [1],
        },
        toy_observation(0),
        [],
        metrics,
        journal,
    )

    expected = [{"hypothesis_id": "H_confirmed", "from": "confirmed", "to": "supported"}]
    assert result["ok"] is True
    assert result["status_normalizations"] == expected
    assert ws.read_hypothesis_ledger()["hypotheses"]["H_confirmed"]["status"] == ("supported")
    records = list(AppendOnlyJournal.read_records(journal.path))
    assert records[-1]["event"] == "hypothesis_revision"
    assert records[-1]["payload"]["status_normalizations"] == expected


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
    # A mismatch is a real counterexample: replaying the unchanged code cannot
    # clear the gate even if the short stored history still happens to pass.
    bt2 = session._dispatch_tool("run_backtest", {}, after, history, metrics, journal)
    assert bt2["certified"] is False
    assert ws.mismatch_blocks_planning is True
    assert "revision" in str(bt2.get("warning", "")).lower()
    ws.write_code(source + "\n# revision after counterexample\n")
    bt3 = session._dispatch_tool("run_backtest", {}, after, history, metrics, journal)
    assert bt3["certified"] is True
    assert ws.mismatch_blocks_planning is False
    bfs = session._dispatch_tool("run_bfs", {}, after, history, metrics, journal)
    assert bfs["found"] is True
    commit2, obs2 = session._handle_commit(
        {
            "kind": "planned",
            "plan_id": bfs["plan_id"],
            "actions": [{"id": 1, "data": {}}],
        },
        after,
        history,
    )
    assert commit2 is not None
    assert obs2["ok"] is True


def test_planned_commit_requires_exact_bfs_plan_binding(tmp_path) -> None:
    env = ToyEnvironment()
    before = env.current
    after = env.step(Action(id=1))
    history = [Transition(before, Action(id=1), after)]
    ws = Workspace(tmp_path / "ws")
    source = """\
def step(state, action):
    nxt = state.copy()
    if int(action["id"]) == 1:
        nxt.frame[0][0] = min(2, int(nxt.frame[0][0]) + 1)
        if int(nxt.frame[0][0]) == 2:
            nxt.state = "WIN"
            nxt.levels_completed = 1
    return nxt

def is_goal(state):
    return state.state == "WIN"
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
    assert session._dispatch_tool("run_backtest", {}, after, history, metrics, journal)["certified"]
    commit, rejected = session._handle_commit(
        {"kind": "planned", "actions": [{"id": 1, "data": {}}]},
        after,
        history,
    )
    assert commit is None
    assert "plan_id" in rejected["error"]
    bfs = session._dispatch_tool("run_bfs", {}, after, history, metrics, journal)
    assert bfs["found"]
    commit, accepted = session._handle_commit(
        {
            "kind": "planned",
            "plan_id": bfs["plan_id"],
            "actions": [{"id": 1, "data": {}}],
        },
        after,
        history,
    )
    assert commit is not None
    assert accepted["plan_id"] == bfs["plan_id"]


def test_experiment_proposal_binds_hypotheses_and_action(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=3,
        max_model_calls=10,
    )
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    current = toy_observation(0)
    registered = session._dispatch_tool(
        "update_hypotheses",
        {
            "hypotheses": [
                {
                    "id": "H_changes",
                    "statement": "The candidate action changes the frame.",
                    "status": "active",
                },
                {
                    "id": "H_fixed",
                    "statement": "The candidate action leaves the frame fixed.",
                    "status": "active",
                },
            ],
            "reason": "initial competing mechanisms",
            "evidence_seq": [1],
        },
        current,
        [],
        metrics,
        journal,
    )
    assert registered["ok"]
    unstructured_commit, unstructured_result = session._handle_commit(
        {
            "kind": "exploration",
            "actions": [{"id": 1, "data": {}}],
            "rationale": "goal-directed navigation need not be a formal experiment",
        },
        current,
        [],
    )
    assert unstructured_commit is not None
    assert unstructured_result["ok"]
    proposal = session._dispatch_tool(
        "propose_experiment",
        {
            "action": {"id": 2, "data": {}},
            "hypotheses": [
                {"id": "H_changes", "prediction": "frame changes"},
                {"id": "H_fixed", "prediction": "frame stays fixed"},
            ],
            "rationale": "separates two mechanisms",
            "evidence_seq": [1],
        },
        current,
        [],
        metrics,
        journal,
    )
    assert proposal["ok"]
    wrong, rejected = session._handle_commit(
        {
            "kind": "exploration",
            "experiment_id": proposal["experiment_id"],
            "actions": [{"id": 1, "data": {}}],
        },
        current,
        [],
    )
    assert wrong is None
    assert "match" in rejected["error"]
    commit, accepted = session._handle_commit(
        {
            "kind": "exploration",
            "experiment_id": proposal["experiment_id"],
            "actions": [{"id": 2, "data": {}}],
        },
        current,
        [],
    )
    assert commit is not None
    assert accepted["experiment_id"] == proposal["experiment_id"]


def test_hypotheses_can_evolve_and_observed_experiment_does_not_block_progress(
    tmp_path,
) -> None:
    ws = Workspace(tmp_path / "ws")
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=3,
        max_model_calls=10,
    )
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    current = toy_observation(0)
    assert session._dispatch_tool(
        "update_hypotheses",
        {
            "hypotheses": [
                {"id": "H_changes", "statement": "Frame changes.", "status": "active"},
                {"id": "H_fixed", "statement": "Frame stays fixed.", "status": "active"},
            ],
            "reason": "register stable alternatives",
            "evidence_seq": [1],
        },
        current,
        [],
        metrics,
        journal,
    )["ok"]
    reused = session._dispatch_tool(
        "update_hypotheses",
        {
            "hypotheses": [
                {
                    "id": "H_changes",
                    "statement": "A different theory hidden behind the same ID.",
                    "status": "active",
                }
            ],
            "reason": "illegal semantic reuse",
            "evidence_seq": [1],
        },
        current,
        [],
        metrics,
        journal,
    )
    assert reused["ok"]
    ledger_after_revision = ws.read_hypothesis_ledger()
    revised = ledger_after_revision["hypotheses"]["H_changes"]
    assert revised["statement"] == "A different theory hidden behind the same ID."
    assert revised["statement_history"]
    proposal = session._dispatch_tool(
        "propose_experiment",
        {
            "action": {"id": 2},
            "hypotheses": [
                {"id": "H_changes", "prediction": "frame changes"},
                {"id": "H_fixed", "prediction": "frame stays fixed"},
            ],
            "rationale": "direct discriminator",
            "evidence_seq": [1],
        },
        current,
        [],
        metrics,
        journal,
    )
    assert proposal["ok"]
    ws.record_experiment_outcome(
        proposal["experiment_id"],
        {"after_fingerprint": current.fingerprint},
        evidence_seq=2,
    )
    next_proposal = session._dispatch_tool(
        "propose_experiment",
        {
            "action": {"id": 1},
            "hypotheses": [
                {"id": "H_changes", "prediction": "changes again"},
                {"id": "H_fixed", "prediction": "stays fixed again"},
            ],
            "rationale": "a higher-value follow-up need not wait for bookkeeping",
            "evidence_seq": [2],
        },
        current,
        [],
        metrics,
        journal,
    )
    assert next_proposal["ok"]
    resolved = session._dispatch_tool(
        "update_hypotheses",
        {
            "hypotheses": [
                {"id": "H_changes", "status": "rejected"},
                {"id": "H_fixed", "status": "supported"},
            ],
            "experiment_id": proposal["experiment_id"],
            "reason": "observed no frame change",
            "evidence_seq": [2],
        },
        current,
        [],
        metrics,
        journal,
    )
    assert resolved["ok"]
    assert metrics.experiments_resolved == 1
    ledger = ws.read_hypothesis_ledger()
    assert ledger["experiments"][proposal["experiment_id"]]["status"] == "reviewed"


def test_navigation_commit_requires_certification_but_not_bfs_plan(tmp_path) -> None:
    env = ToyEnvironment()
    before = env.current
    after = env.step(Action(id=1))
    history = [Transition(before, Action(id=1), after)]
    ws = Workspace(tmp_path / "ws")
    source = """\
def step(state, action):
    nxt = state.copy()
    if int(action["id"]) == 1:
        nxt.frame[0][0] = min(2, int(nxt.frame[0][0]) + 1)
        if int(nxt.frame[0][0]) == 2:
            nxt.state = "WIN"
            nxt.levels_completed = 1
    return nxt

def is_goal(state):
    return state.state == "WIN"
"""
    ws.write_code(source)
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=4,
        max_model_calls=10,
    )
    rejected, result = session._handle_commit(
        {
            "kind": "navigation",
            "actions": [{"id": 2}, {"id": 1}],
        },
        after,
        history,
    )
    assert rejected is None
    assert "certified" in result["error"]

    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    assert session._dispatch_tool("run_backtest", {}, after, history, metrics, journal)["certified"]
    commit, accepted = session._handle_commit(
        {
            "kind": "navigation",
            "actions": [{"id": 2}, {"id": 1}],
            "rationale": "move through a known safe staging state before the target",
        },
        after,
        history,
    )
    assert commit is not None
    assert commit.kind == "navigation"
    assert commit.plan_id is None
    assert accepted["accepted"] == 2

    ws.record_mismatch({"reason": "counterexample"})
    blocked, blocked_result = session._handle_commit(
        {
            "kind": "navigation",
            "actions": [{"id": 2}, {"id": 1}],
        },
        after,
        history,
    )
    assert blocked is None
    assert "blocked" in blocked_result["error"]


def test_is_goal_only_route_stays_navigation_until_boundary_event_is_modeled(
    tmp_path,
) -> None:
    before = toy_observation(0)
    current = toy_observation(1)
    history = [Transition(before, Action(id=1), current)]
    ws = Workspace(tmp_path / "ws")
    no_boundary_event = """\
def init_state(entry_grid):
    return {"position": int(entry_grid[0][0])}

def predict(latent, grid, action):
    nxt = deepcopy(grid)
    state = deepcopy(latent)
    if int(action["id"]) == 1:
        state["position"] = min(2, int(state["position"]) + 1)
        nxt[0][0] = state["position"]
    return nxt, [], state

def is_goal(latent, grid):
    return int(latent["position"]) >= 2
"""
    ws.write_code(no_boundary_event)
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=4,
        max_model_calls=10,
    )
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    assert session._dispatch_tool("run_backtest", {}, current, history, metrics, journal)[
        "certified"
    ]

    bfs = session._dispatch_tool("run_bfs", {}, current, history, metrics, journal)
    assert bfs["found"] is False
    assert "does not predict level progress" in bfs["error"]
    navigation, accepted = session._handle_commit(
        {
            "kind": "navigation",
            "actions": [{"id": 2}, {"id": 1}],
            "rationale": "monitored route while the boundary mechanism is unknown",
        },
        current,
        history,
    )
    assert navigation is not None
    assert accepted["accepted"] == 2

    with_boundary_event = no_boundary_event.replace(
        "return nxt, [], state",
        'return nxt, (["LEVEL_COMPLETE"] if state["position"] >= 2 else []), state',
    )
    ws.write_code(with_boundary_event)
    assert session._dispatch_tool("run_backtest", {}, current, history, metrics, journal)[
        "certified"
    ]
    planned = session._dispatch_tool("run_bfs", {}, current, history, metrics, journal)
    assert planned["found"] is True
    assert [step["action"]["id"] for step in planned["steps"]] == [1]


def test_approximate_certification_allows_navigation_but_not_bfs(tmp_path) -> None:
    before = Observation(
        game_id="toy",
        state="NOT_FINISHED",
        levels_completed=0,
        win_levels=1,
        available_actions=(1,),
        frame=tuple(tuple(0 for _ in range(64)) for _ in range(64)),
    )
    rows = [list(row) for row in before.frame]
    rows[-1][-1] = 1
    after = Observation(
        game_id="toy",
        state="NOT_FINISHED",
        levels_completed=0,
        win_levels=1,
        available_actions=(1,),
        frame=tuple(tuple(row) for row in rows),
    )
    history = [Transition(before, Action(1), after)]
    ws = Workspace(tmp_path / "ws")
    ws.write_code(
        "def step(state, action):\n"
        "    return state.copy()\n\n"
        "def is_goal(state):\n"
        "    return False\n"
    )
    session = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=2,
        planner_max_nodes=20,
        max_plan_steps=3,
        max_model_calls=4,
        allow_approximate_visual_matches=True,
    )
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    result = session._dispatch_tool("run_backtest", {}, after, history, metrics, journal)
    assert result["certified"] is True
    assert result["certified_exact"] is False
    bfs = session._dispatch_tool("run_bfs", {}, after, history, metrics, journal)
    assert bfs["ok"] is False
    assert "exact" in bfs["error"]
    commit, accepted = session._handle_commit(
        {"kind": "navigation", "actions": [{"id": 1}, {"id": 1}]},
        after,
        history,
    )
    assert commit is not None
    assert accepted["kind"] == "navigation"


def test_bfs_no_plan_cooldown_survives_deliberation_sessions(tmp_path) -> None:
    env = ToyEnvironment()
    before = env.current
    after = env.step(Action(id=1))
    history = [Transition(before, Action(id=1), after)]
    ws = Workspace(tmp_path / "ws")
    ws.write_code(
        """\
def step(state, action):
    nxt = state.copy()
    if int(action["id"]) == 1:
        nxt.frame[0][0] = min(1, int(nxt.frame[0][0]) + 1)
    return nxt

def is_goal(state):
    return False
"""
    )
    journal = AppendOnlyJournal(tmp_path / "j.jsonl")
    metrics = RunMetrics(agent="harness", game_id="toy", run_index=0, seed=0)
    first = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=4,
        max_model_calls=10,
        env_actions_so_far=1,
    )
    assert first._dispatch_tool("run_backtest", {}, after, history, metrics, journal)["certified"]
    no_plan = first._dispatch_tool("run_bfs", {}, after, history, metrics, journal)
    assert no_plan["found"] is False
    assert no_plan["cached"] is False
    assert metrics.bfs_no_plan_results == 1

    second = DeliberationSession(
        DeterministicMockClient(),
        ws,
        max_turns=4,
        planner_max_nodes=20,
        max_plan_steps=4,
        max_model_calls=10,
        env_actions_so_far=2,
    )
    cached = second._dispatch_tool("run_bfs", {}, after, history, metrics, journal)
    assert cached["found"] is False
    assert cached["cached"] is True
    assert cached["bfs_advisory"]["cooldown_actions_remaining"] == 7
    assert metrics.bfs_no_plan_cache_hits == 1


def test_hypothesis_prompt_context_omits_lineage_and_large_deltas(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    items = [
        {
            "id": f"H_candidate_{index}",
            "statement": f"candidate {index} " + "x" * 900,
            "status": "active",
        }
        for index in range(12)
    ]
    ws.update_hypotheses(items, evidence_seq=list(range(40)), reason="r" * 800)
    ws.update_hypotheses(
        [
            {
                "id": item["id"],
                "statement": f"revised {item['id']} " + "y" * 900,
                "status": "active",
            }
            for item in items
        ],
        evidence_seq=list(range(40, 80)),
        reason="new evidence " + "z" * 800,
    )
    version = ws.register_experiment(
        {
            "experiment_id": "exp-context",
            "action": {"id": 1, "data": {}},
            "current_fingerprint": "fp",
            "hypotheses": [
                {"id": "H_candidate_0", "prediction": "p" * 500},
                {"id": "H_candidate_1", "prediction": "q" * 500},
            ],
            "rationale": "route test " + "r" * 500,
            "evidence_seq": [1, 2],
        }
    )
    assert version > 0
    ws.record_experiment_outcome(
        "exp-context",
        {
            "action": {"id": 1, "data": {}},
            "levels_before": 0,
            "levels_after": 0,
            "state_after": "NOT_FINISHED",
            "delta": {
                "bbox": {"x0": 0, "x1": 63, "y0": 0, "y1": 63},
                "metadata": {},
                "rows": [{"y": index, "rle": "3:64"} for index in range(64)],
            },
        },
        evidence_seq=3,
    )
    context = ws.hypothesis_context(max_chars=3000)
    encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    assert len(encoded) <= 3000
    assert context["context_chars"] == len(encoded)
    assert "statement_history" not in encoded
    assert '"rows"' not in encoded
    assert context["context_truncated"] is True
    roomy = json.dumps(
        ws.hypothesis_context(max_chars=20000),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert "changed_row_count" in roomy
    assert '"rows"' not in roomy
