from __future__ import annotations

import pytest

from arc_schema.core import Action, Transition
from arc_schema.mock import toy_observation
from arc_schema.program_world_model import (
    ProgramWorldModel,
    backtest_program,
    bfs_program_plan,
)
from arc_schema.sandbox import SandboxError, validate_source


TOY_CORRECT = '''\
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
'''

TOY_WRONG = '''\
def step(state, action):
    nxt = state.copy()
    nxt.frame[0][0] = 9
    return nxt

def is_goal(state):
    return False
'''


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


def test_missing_step_rejected() -> None:
    with pytest.raises(SandboxError, match="step"):
        ProgramWorldModel("def is_goal(state):\n    return False\n")
