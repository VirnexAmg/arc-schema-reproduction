from __future__ import annotations

import pytest

from arc_schema.core import Action, Observation, Transition
from arc_schema.mock import toy_observation
from arc_schema.program_world_model import (
    HARD_MAX_SOURCE_LINES,
    MAX_SOURCE_LINES,
    ProgramWorldModel,
    audit_world_model_source,
    backtest_program,
    bfs_program_plan,
    world_model_complexity_warnings,
)
from arc_schema.sandbox import SandboxError, validate_source


TOY_CORRECT = """\
def step(state, action):
    nxt = state.copy()
    aid = int(action["id"])
    # ToyEnvironment: action 1 advances position stored in frame[0][0]
    if aid == 1:
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

TOY_WRONG = """\
def step(state, action):
    nxt = state.copy()
    nxt.frame[0][0] = 9
    return nxt

def is_goal(state):
    return False
"""


def test_sandbox_rejects_imports() -> None:
    with pytest.raises(SandboxError, match="import"):
        validate_source("import os\ndef step(state, action):\n    return state\n")


def test_sandbox_rejects_dunder_access() -> None:
    with pytest.raises(SandboxError, match="dunder"):
        validate_source(
            "def step(state, action):\n    return state.__class__\n"
            "def is_goal(state):\n    return False\n"
        )


def test_program_backtest_accepts_correct_toy_model() -> None:
    history = [
        Transition(toy_observation(0), Action(1), toy_observation(1)),
        Transition(toy_observation(1), Action(1), toy_observation(2)),
    ]
    model = ProgramWorldModel(TOY_CORRECT)
    result = backtest_program(model, history)
    assert result.passed
    assert result.checked == 2


def test_program_backtest_reports_first_mismatch() -> None:
    history = [Transition(toy_observation(0), Action(1), toy_observation(1))]
    model = ProgramWorldModel(TOY_WRONG)
    result = backtest_program(model, history)
    assert not result.passed
    assert result.mismatch_index == 0


def test_bfs_finds_toy_goal() -> None:
    model = ProgramWorldModel(TOY_CORRECT)
    plan = bfs_program_plan(model, toy_observation(0), max_nodes=50, max_depth=5)
    assert plan is not None
    assert [step.action.id for step in plan] == [1, 1]


def test_bfs_uses_actions_exposed_by_each_predicted_state() -> None:
    source = """\
def step(state, action):
    nxt = state.copy()
    aid = int(action["id"])
    pos = int(nxt.frame[0][0])
    if pos == 0 and aid == 1:
        nxt.frame[0][0] = 1
        nxt.available_actions = [2]
    elif pos == 1 and aid == 2:
        nxt.frame[0][0] = 2
        nxt.state = "WIN"
        nxt.levels_completed = 1
    return nxt

def is_goal(state):
    return state.state == "WIN"
"""
    start = Observation(
        game_id="toy",
        state="NOT_FINISHED",
        levels_completed=0,
        win_levels=1,
        available_actions=(1,),
        frame=((0, 0, 0),),
    )
    plan = bfs_program_plan(ProgramWorldModel(source), start, max_nodes=20, max_depth=3)
    assert plan is not None
    assert [step.action.id for step in plan] == [1, 2]


def test_missing_step_rejected() -> None:
    with pytest.raises(SandboxError, match="step"):
        ProgramWorldModel("def is_goal(state):\n    return False\n")


def test_static_audit_warns_on_trajectory_sized_rle_literal_dump() -> None:
    dumped = ",".join(f"{index}:1" for index in range(120))
    source = f'''\
FRAME = "{dumped}"
def step(state, action):
    return state
def is_goal(state):
    return False
'''
    assert not audit_world_model_source(source)
    assert any("RLE runs" in warning for warning in world_model_complexity_warnings(source))
    ProgramWorldModel(source)


def test_source_size_target_warns_without_blocking_useful_model() -> None:
    padding = "\n".join(f"# patch {index}" for index in range(MAX_SOURCE_LINES + 1))
    source = (
        padding
        + "\ndef step(state, action):\n    return state\n"
        + "def is_goal(state):\n    return False\n"
    )
    assert audit_world_model_source(source) == []
    assert any("source lines" in warning for warning in world_model_complexity_warnings(source))
    ProgramWorldModel(source)


def test_extreme_source_growth_remains_a_hard_safety_rejection() -> None:
    padding = "\n".join(f"# runaway patch {index}" for index in range(HARD_MAX_SOURCE_LINES + 1))
    source = (
        padding
        + "\ndef step(state, action):\n    return state\n"
        + "def is_goal(state):\n    return False\n"
    )
    assert any("hard limit" in blocker for blocker in audit_world_model_source(source))
    with pytest.raises(SandboxError, match="static audit"):
        ProgramWorldModel(source)


def test_backtest_accepts_small_instrumental_visual_error() -> None:
    before = Observation(
        game_id="toy",
        state="NOT_FINISHED",
        levels_completed=0,
        win_levels=1,
        available_actions=(1,),
        frame=tuple(tuple(0 for _ in range(64)) for _ in range(64)),
    )
    after_rows = [list(row) for row in before.frame]
    after_rows[63][63] = 1
    after = Observation(
        game_id="toy",
        state="NOT_FINISHED",
        levels_completed=0,
        win_levels=1,
        available_actions=(1,),
        frame=tuple(tuple(row) for row in after_rows),
    )
    source = """\
def step(state, action):
    return state.copy()

def is_goal(state):
    return False
"""
    result = backtest_program(
        ProgramWorldModel(source),
        [Transition(before, Action(1), after)],
        allow_approximate=True,
    )
    assert result.passed
    assert result.approximate_matches == 1
    strict = backtest_program(
        ProgramWorldModel(source),
        [Transition(before, Action(1), after)],
    )
    assert not strict.passed


def test_approximate_matching_never_accepts_false_level_progress() -> None:
    source = """\
def init_state(entry_grid):
    return {}

def predict(latent, grid, action):
    return deepcopy(grid), ["LEVEL_COMPLETE"], deepcopy(latent)

def is_goal(latent, grid):
    return True
"""
    before = toy_observation(0)
    unchanged = toy_observation(0)
    result = backtest_program(
        ProgramWorldModel(source),
        [Transition(before, Action(1), unchanged)],
    )
    assert not result.passed
    assert result.reason == "predicted state differs from historical observation"


def test_latent_event_api_backtests_level_boundary_without_inventing_entry_frame() -> None:
    source = """\
def init_state(entry_grid):
    return {"position": int(entry_grid[0][0])}

def predict(latent, grid, action):
    nxt = deepcopy(grid)
    state = deepcopy(latent)
    events = []
    if int(action["id"]) == 1:
        state["position"] = min(2, int(state["position"]) + 1)
        nxt[0][0] = state["position"]
        if state["position"] == 2:
            events.append("LEVEL_COMPLETE")
    return nxt, events, state

def is_goal(latent, grid):
    return int(latent["position"]) >= 2
"""
    start = toy_observation(0)
    middle = toy_observation(1)
    # The environment reveals a completely new level-entry grid. The model only
    # needs to predict LEVEL_COMPLETE, not fabricate this unseen frame.
    next_level = Observation(
        game_id="toy",
        state="NOT_FINISHED",
        levels_completed=1,
        win_levels=2,
        available_actions=(1, 2),
        frame=((9, 9, 9), (9, 0, 9)),
        frame_count=3,
    )
    history = [
        Transition(start, Action(1), middle),
        Transition(middle, Action(1), next_level),
    ]
    model = ProgramWorldModel(source)
    result = backtest_program(model, history)
    assert result.passed
    assert result.checked == 2
    assert result.checked_by_action == {"1": 2}
    plan = bfs_program_plan(model, start, max_nodes=50, max_depth=5)
    assert plan is not None
    assert [step.action.id for step in plan] == [1, 1]
