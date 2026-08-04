from __future__ import annotations

import struct

from arc_schema.context import frame_png_bytes, next_explore_action
from arc_schema.core import Action, Transition
from arc_schema.mock import toy_observation


def test_exploration_balances_actions_across_changing_exact_frames() -> None:
    before = toy_observation(0)
    after = toy_observation(1)
    history = [Transition(before, Action(1), after)]
    assert before.fingerprint != after.fingerprint
    assert next_explore_action(after, history) == Action(2)


def test_vision_png_is_upscaled_truecolour() -> None:
    png = frame_png_bytes(toy_observation(0))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
    assert max(width, height) >= 500
    assert bit_depth == 8
    assert color_type == 2
