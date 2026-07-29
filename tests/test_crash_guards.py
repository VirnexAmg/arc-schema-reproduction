from __future__ import annotations

import json

import pytest

from arc_schema.context import next_explore_action
from arc_schema.core import Action, Observation, Transition
from arc_schema.deepseek_client import _parse_json
from arc_schema.mock import ToyEnvironment, toy_observation


def test_next_explore_action_skips_game_over() -> None:
    current = toy_observation(0, state="GAME_OVER")
    # Even if available_actions look playable, explore must refuse.
    assert current.available_actions == (0,)
    assert next_explore_action(current, []) is None


def test_transition_delta_tolerates_height_mismatch() -> None:
    before = Observation(
        game_id="toy",
        state="GAME_OVER",
        levels_completed=1,
        win_levels=7,
        available_actions=(1, 2, 3, 4),
        frame=tuple((0,) * 4 for _ in range(4)),
    )
    after = Observation(
        game_id="toy",
        state="GAME_OVER",
        levels_completed=1,
        win_levels=7,
        available_actions=(0,),
        frame=tuple((1,) * 4 for _ in range(2)),  # different height
    )
    transition = Transition(before, Action(id=1), after)
    delta = transition.delta()
    assert delta.metadata.get("frame_geometry_changed") is True
    assert delta.changed_rows == ()
    # Journaling path must not raise.
    payload = transition.to_dict()
    assert "before" in payload and "after" in payload


def test_toy_environment_rejects_non_reset_after_game_over() -> None:
    env = ToyEnvironment(lethal_action=2)
    env.step(Action(id=2))
    assert env.current.state == "GAME_OVER"
    with pytest.raises(ValueError):
        env.step(Action(id=1))
    env.step(Action(id=0))
    assert env.current.state == "NOT_FINISHED"


def test_parse_json_tolerates_trailing_extra_data() -> None:
    text = '{"tool":"run_backtest","args":{}}\nnote: done'
    value = _parse_json(text)
    assert value["tool"] == "run_backtest"
    # Still rejects non-object payloads.
    with pytest.raises((json.JSONDecodeError, ValueError)):
        _parse_json("[1,2,3]")
