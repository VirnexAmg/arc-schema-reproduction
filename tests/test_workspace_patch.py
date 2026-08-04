from __future__ import annotations

import pytest

from arc_schema.program_world_model import DEFAULT_WORLD_MODEL_STUB
from arc_schema.workspace import Workspace


def test_workspace_apply_patch_unique(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    assert (
        "identity transition" in ws.read_code()
        or "Identity" in ws.read_code()
        or "nxt" in ws.read_code()
    )
    old = "return nxt"
    new = "nxt.state = state.state\n    return nxt"
    ws.apply_patch(old, new)
    assert "nxt.state = state.state" in ws.read_code()
    assert ws.version >= 2
    assert ws.certified is False


def test_workspace_apply_patch_requires_unique_match(tmp_path) -> None:
    ws = Workspace(tmp_path / "ws")
    ws.write_code(DEFAULT_WORLD_MODEL_STUB + "\n# pad\n")
    with pytest.raises(ValueError, match="not found"):
        ws.apply_patch("this-string-is-absent", "x")
