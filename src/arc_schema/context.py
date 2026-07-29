from __future__ import annotations

import base64
import struct
import zlib
from collections import Counter
from typing import Any

from arc_schema.core import Action, Observation, Transition, canonical_json


JsonDict = dict[str, Any]


def untried_actions(
    current: Observation,
    history: list[Transition],
) -> list[int]:
    """Return available action ids that have not been tried from the current fingerprint."""
    tried = {
        item.action.id
        for item in history
        if item.before.fingerprint == current.fingerprint and not item.action.data
    }
    return [action_id for action_id in current.available_actions if action_id not in tried]


def next_explore_action(
    current: Observation,
    history: list[Transition],
) -> Action | None:
    """Pick an explore action; prefer untried, else least-used at this fingerprint.

    Avoids collapsing to available_actions[0] forever after the first full sweep
    (which biased DeepSeek forced-explore toward action 1).
    Never explores from terminal states — outer harness must RESET first.
    """
    if current.state in {"GAME_OVER", "WIN", "NOT_PLAYED"}:
        return None
    candidates = untried_actions(current, history)
    if candidates:
        for action_id in candidates:
            if action_id != 6:
                return Action(id=action_id)
        return Action(id=candidates[0])

    pool = [action_id for action_id in current.available_actions if action_id != 6]
    if not pool:
        pool = list(current.available_actions)
    if not pool:
        return None

    counts: Counter[int] = Counter()
    for item in history:
        if item.before.fingerprint == current.fingerprint and not item.action.data:
            counts[item.action.id] += 1
    return Action(id=min(pool, key=lambda action_id: (counts[action_id], action_id)))


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def frame_png_bytes(observation: Observation) -> bytes:
    """Encode the observation frame as an 8-bit grayscale PNG without external deps."""
    if not observation.frame:
        raise ValueError("observation has no frame")
    height = len(observation.frame)
    width = len(observation.frame[0])
    raw = bytearray()
    for row in observation.frame:
        raw.append(0)  # filter: None
        for cell in row:
            raw.append(min(255, int(cell) * 16))
    compressed = zlib.compress(bytes(raw), level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def frame_png_base64(observation: Observation) -> str:
    return base64.b64encode(frame_png_bytes(observation)).decode("ascii")


def local_observation_catalog(
    current: Observation,
    history: list[Transition],
    *,
    limit: int,
) -> dict[str, JsonDict]:
    """Authoritative local catalog used to materialize snapshot refs/patches."""
    catalog: dict[str, JsonDict] = {f"obs_{current.fingerprint}": current.snapshot()}
    for item in history[-limit:]:
        catalog[f"obs_{item.before.fingerprint}"] = item.before.snapshot()
        catalog[f"obs_{item.after.fingerprint}"] = item.after.snapshot()
    return catalog


def build_compact_context(
    current: Observation,
    history: list[Transition],
    *,
    limit: int,
    vision_enabled: bool = False,
) -> tuple[JsonDict, list[dict[str, Any]] | None]:
    """
    Build a shared compact context for baseline and harness.

    Current observation always includes the authoritative full frame_rle.
    History entries use sparse deltas only.
    """
    current_ref = f"obs_{current.fingerprint}"
    compact_history: list[JsonDict] = []
    for item in history[-limit:]:
        compact_history.append(
            {
                "before_fingerprint": item.before.fingerprint,
                "before_ref": f"obs_{item.before.fingerprint}",
                "action": {"id": item.action.id, "data": item.action.data},
                "after_fingerprint": item.after.fingerprint,
                "after_ref": f"obs_{item.after.fingerprint}",
                "delta": item.delta().to_dict(),
            }
        )

    payload: JsonDict = {
        "current": {
            "snapshot_ref": current_ref,
            "snapshot": current.snapshot(),
            "fingerprint": current.fingerprint,
            "available_actions": list(current.available_actions),
            "untried_action_ids": untried_actions(current, history),
        },
        "history_deltas": compact_history,
        "notes": [
            "current.snapshot is authoritative and complete",
            "history_deltas are sparse frame/metadata changes only",
            "action meanings must be inferred from observed transitions",
            "do not assume ACTION1-4 semantics from external game source",
        ],
    }

    vision_parts: list[dict[str, Any]] | None = None
    if vision_enabled:
        png = frame_png_base64(current)
        vision_parts = [
            {
                "type": "text",
                "text": (
                    "Current frame as PNG. Use it together with the JSON context. "
                    + canonical_json(payload)
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{png}"},
            },
        ]
    return payload, vision_parts
