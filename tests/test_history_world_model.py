from __future__ import annotations

import json

import pytest

from arc_schema.backtest import backtest
from arc_schema.core import (
    Action,
    Observation,
    Transition,
    apply_frame_delta,
    compute_frame_delta,
    encode_row,
    frame_to_rle,
    materialize_snapshot,
)
from arc_schema.history import AppendOnlyJournal, HistoryIntegrityError
from arc_schema.planner import bfs_plan
from arc_schema.world_model import DeclarativeWorldModel, WorldModelValidationError


def observation(position: int) -> Observation:
    return Observation(
        game_id="toy",
        state="WIN" if position == 2 else "NOT_FINISHED",
        levels_completed=int(position == 2),
        win_levels=1,
        available_actions=(1,),
        frame=((position,),),
    )


def model(after_position: int = 1) -> DeclarativeWorldModel:
    return DeclarativeWorldModel.from_dict(
        {
            "states": [
                {"id": "s0", "snapshot": observation(0).snapshot()},
                {"id": "s1", "snapshot": observation(after_position).snapshot()},
                {"id": "s2", "snapshot": observation(2).snapshot(), "goal": True},
            ],
            "transitions": [
                {"from": "s0", "action": {"id": 1}, "to": "s1"},
                {"from": "s1", "action": {"id": 1}, "to": "s2"},
            ],
        },
        allow_raw_snapshots=True,
    )


def test_journal_detects_tampering(tmp_path) -> None:
    path = tmp_path / "history.jsonl"
    journal = AppendOnlyJournal(path)
    journal.append("observation", {"value": 1})
    journal.append("transition", {"value": 2})
    records = list(AppendOnlyJournal.read_records(path))
    assert AppendOnlyJournal.verify(records) == records[-1]["record_hash"]

    records[0]["payload"]["value"] = 999
    path.write_text("\n".join(json.dumps(item) for item in records) + "\n")
    with pytest.raises(HistoryIntegrityError, match="modified history record 0"):
        AppendOnlyJournal(path)


def test_backtest_accepts_correct_model_and_reports_first_mismatch() -> None:
    history = [
        Transition(observation(0), Action(1), observation(1)),
        Transition(observation(1), Action(1), observation(2)),
    ]
    passed = backtest(model(), history)
    assert passed.passed
    assert passed.checked == 2

    failed = backtest(model(after_position=9), history)
    assert not failed.passed
    assert failed.mismatch_index == 0
    assert failed.predicted == observation(9).snapshot()
    assert failed.actual == observation(1).snapshot()


def test_backtest_limit_matches_context_window() -> None:
    """Full-history backtest would fail; windowed backtest matches the prompt."""
    history = [
        Transition(observation(0), Action(1), observation(1)),
        Transition(observation(1), Action(1), observation(0)),
        Transition(observation(0), Action(1), observation(1)),
    ]
    # Model only knows the last transition's states.
    window_model = DeclarativeWorldModel.from_dict(
        {
            "states": [
                {"id": "s0", "snapshot": observation(0).snapshot()},
                {"id": "s1", "snapshot": observation(1).snapshot()},
            ],
            "transitions": [
                {"from": "s0", "action": {"id": 1}, "to": "s1"},
            ],
        },
        allow_raw_snapshots=True,
    )
    assert not backtest(window_model, history).passed
    windowed = backtest(window_model, history, limit=1)
    assert windowed.passed
    assert windowed.checked == 1


def test_history_skeleton_and_extension_merge() -> None:
    from arc_schema.world_model import build_history_skeleton, merge_world_model_extension

    current = observation(1)
    history = [Transition(observation(0), Action(1), observation(1))]
    skeleton = build_history_skeleton(current, history, limit=12)
    assert skeleton["current_state_id"] in {s["id"] for s in skeleton["states"]}
    assert len(skeleton["transitions"]) == 1

    extension = {
        "states": [
            {
                "id": "g0",
                "base_ref": f"obs_{current.fingerprint}",
                "snapshot_patch": {
                    "rows": [{"y": 0, "rle": encode_row((2,))}],
                    "metadata": {
                        "state": "WIN",
                        "levels_completed": 1,
                        "available_actions": [1],
                    },
                },
                "goal": True,
            }
        ],
        "transitions": [
            {
                "from": skeleton["current_state_id"],
                "action": {"id": 1, "data": {}},
                "to": "g0",
            }
        ],
    }
    merged = merge_world_model_extension(skeleton, extension)
    catalog = {
        f"obs_{observation(0).fingerprint}": observation(0).snapshot(),
        f"obs_{current.fingerprint}": current.snapshot(),
    }
    model = DeclarativeWorldModel.from_dict(merged, catalog=catalog, known_levels=0)
    assert backtest(model, history, limit=12).passed
    assert model.goal_state_ids()
    start = model.state_for_observation(current)
    assert start is not None
    plan = bfs_plan(model, start.id, max_nodes=10, max_depth=3)
    assert plan is not None
    assert [step.action.id for step in plan] == [1]


def test_bfs_finds_shortest_toy_plan() -> None:
    plan = bfs_plan(model(), "s0", max_nodes=10)
    assert plan is not None
    assert [step.action.id for step in plan] == [1, 1]
    assert [step.predicted_state_id for step in plan] == ["s1", "s2"]


def test_world_model_resolves_authoritative_snapshot_reference() -> None:
    expected = observation(0).snapshot()
    resolved = DeclarativeWorldModel.from_dict(
        {
            "states": [{"id": "s0", "snapshot_ref": "known"}],
            "transitions": [],
        },
        known_snapshots={"known": expected},
    )
    assert resolved.states["s0"].snapshot == expected


def test_frame_delta_round_trip() -> None:
    before = ((0, 0, 1), (2, 2, 2), (3, 0, 0))
    after = ((0, 9, 1), (2, 2, 2), (3, 0, 7))
    delta = compute_frame_delta(before, after)
    assert [y for y, _ in delta.changed_rows] == [0, 2]
    assert delta.bbox == (0, 1, 2, 2)
    restored = apply_frame_delta(frame_to_rle(before), delta)
    assert restored == frame_to_rle(after)


def test_snapshot_patch_materialize_and_strict_compare() -> None:
    base = observation(0).snapshot()
    target = observation(1).snapshot()
    rows = []
    for y, (left, right) in enumerate(zip(base["frame_rle"], target["frame_rle"], strict=True)):
        if left != right:
            rows.append({"y": y, "rle": right})
    patch = {
        "rows": rows,
        "metadata": {
            "state": target["state"],
            "levels_completed": target["levels_completed"],
            "available_actions": target["available_actions"],
        },
    }
    materialized = materialize_snapshot(base, patch=patch)
    assert materialized == target


def test_world_model_rejects_raw_snapshot_and_invented_levels() -> None:
    catalog = {"obs": observation(0).snapshot()}
    with pytest.raises(WorldModelValidationError, match="raw snapshot"):
        DeclarativeWorldModel.from_dict(
            {
                "states": [{"id": "s0", "snapshot": observation(0).snapshot()}],
                "transitions": [],
            },
            catalog=catalog,
        )
    with pytest.raises(WorldModelValidationError, match="levels_completed"):
        DeclarativeWorldModel.from_dict(
            {
                "states": [
                    {
                        "id": "s1",
                        "base_ref": "obs",
                        "snapshot_patch": {
                            "rows": [{"y": 0, "rle": encode_row((1,))}],
                            "metadata": {"levels_completed": 9},
                        },
                        "goal": True,
                    }
                ],
                "transitions": [],
            },
            catalog=catalog,
            known_levels=0,
        )
    ok = DeclarativeWorldModel.from_dict(
        {
            "states": [
                {
                    "id": "s1",
                    "base_ref": "obs",
                    "snapshot_patch": {
                        "rows": [{"y": 0, "rle": encode_row((2,))}],
                        "metadata": {"levels_completed": 1, "state": "WIN"},
                    },
                    "goal": True,
                }
            ],
            "transitions": [],
        },
        catalog=catalog,
        known_levels=0,
    )
    assert ok.states["s1"].snapshot["levels_completed"] == 1
