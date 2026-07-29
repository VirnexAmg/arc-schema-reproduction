from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


JsonDict = dict[str, Any]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Action:
    id: int
    data: JsonDict = field(default_factory=dict)

    def key(self) -> str:
        return canonical_json({"id": self.id, "data": self.data})


def encode_row(row: tuple[int, ...] | list[int]) -> str:
    if not row:
        return ""
    runs: list[str] = []
    current = int(row[0])
    count = 1
    for cell in row[1:]:
        value = int(cell)
        if value == current:
            count += 1
        else:
            runs.append(f"{current}:{count}")
            current, count = value, 1
    runs.append(f"{current}:{count}")
    return ",".join(runs)


def decode_row(encoded: str, width: int | None = None) -> list[int]:
    if not encoded:
        return []
    cells: list[int] = []
    for run in encoded.split(","):
        if not run:
            continue
        value_text, count_text = run.split(":", 1)
        cells.extend([int(value_text)] * int(count_text))
    if width is not None and len(cells) != width:
        raise ValueError(f"decoded row width {len(cells)} != expected {width}")
    return cells


@dataclass(frozen=True)
class FrameDelta:
    """Sparse row-level difference between two frames."""

    changed_rows: tuple[tuple[int, str], ...] = ()
    bbox: tuple[int, int, int, int] | None = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        value: JsonDict = {
            "rows": [{"y": y, "rle": rle} for y, rle in self.changed_rows],
            "metadata": dict(self.metadata),
        }
        if self.bbox is not None:
            value["bbox"] = {
                "y0": self.bbox[0],
                "x0": self.bbox[1],
                "y1": self.bbox[2],
                "x1": self.bbox[3],
            }
        return value

    @classmethod
    def from_dict(cls, value: JsonDict) -> FrameDelta:
        rows = tuple((int(item["y"]), str(item["rle"])) for item in value.get("rows", []))
        bbox_value = value.get("bbox")
        bbox = None
        if isinstance(bbox_value, dict):
            bbox = (
                int(bbox_value["y0"]),
                int(bbox_value["x0"]),
                int(bbox_value["y1"]),
                int(bbox_value["x1"]),
            )
        return cls(changed_rows=rows, bbox=bbox, metadata=dict(value.get("metadata", {})))


def frame_to_rle(frame: tuple[tuple[int, ...], ...]) -> list[str]:
    return [encode_row(row) for row in frame]


def rle_to_frame(rows: list[str]) -> tuple[tuple[int, ...], ...]:
    if not rows:
        return ()
    decoded = [tuple(decode_row(row)) for row in rows]
    width = len(decoded[0])
    for row in decoded[1:]:
        if len(row) != width:
            raise ValueError("inconsistent RLE frame widths")
    return tuple(decoded)


def compute_frame_delta(
    before: tuple[tuple[int, ...], ...],
    after: tuple[tuple[int, ...], ...],
) -> FrameDelta:
    if not before and not after:
        return FrameDelta()
    if len(before) != len(after):
        raise ValueError("frame heights must match for delta computation")
    changed: list[tuple[int, str]] = []
    min_x = min_y = max_x = max_y = None
    for y, (before_row, after_row) in enumerate(zip(before, after, strict=True)):
        if before_row == after_row:
            continue
        changed.append((y, encode_row(after_row)))
        for x, (left, right) in enumerate(zip(before_row, after_row, strict=True)):
            if left != right:
                min_x = x if min_x is None else min(min_x, x)
                max_x = x if max_x is None else max(max_x, x)
                min_y = y if min_y is None else min(min_y, y)
                max_y = y if max_y is None else max(max_y, y)
    bbox = None
    if min_x is not None and min_y is not None and max_x is not None and max_y is not None:
        bbox = (min_y, min_x, max_y, max_x)
    return FrameDelta(changed_rows=tuple(changed), bbox=bbox)


def apply_frame_delta(
    base_rle: list[str],
    delta: FrameDelta,
) -> list[str]:
    result = list(base_rle)
    width = len(decode_row(result[0])) if result else None
    for y, rle in delta.changed_rows:
        if y < 0 or y >= len(result):
            raise ValueError(f"delta row {y} out of bounds for height {len(result)}")
        decode_row(rle, width)
        result[y] = rle
    return result


def metadata_delta(before: JsonDict, after: JsonDict) -> JsonDict:
    keys = ("state", "levels_completed", "win_levels", "available_actions", "game_id")
    changes: JsonDict = {}
    for key in keys:
        if before.get(key) != after.get(key):
            changes[key] = after.get(key)
    return changes


def materialize_snapshot(
    base: JsonDict,
    *,
    patch: JsonDict | None = None,
    delta: FrameDelta | None = None,
) -> JsonDict:
    """Build a full canonical snapshot from a base plus optional patch/delta."""
    snapshot = {
        "game_id": base["game_id"],
        "state": base["state"],
        "levels_completed": base["levels_completed"],
        "win_levels": base["win_levels"],
        "available_actions": list(base["available_actions"]),
        "frame_rle": list(base["frame_rle"]),
    }
    if delta is not None:
        snapshot["frame_rle"] = apply_frame_delta(snapshot["frame_rle"], delta)
        snapshot.update(delta.metadata)
    if patch is not None:
        rows = [(int(item["y"]), str(item["rle"])) for item in patch.get("rows", [])]
        frame_delta = FrameDelta(
            changed_rows=tuple(rows),
            metadata=dict(patch.get("metadata", {})),
        )
        snapshot["frame_rle"] = apply_frame_delta(snapshot["frame_rle"], frame_delta)
        snapshot.update(frame_delta.metadata)
    return snapshot


@dataclass(frozen=True)
class Observation:
    game_id: str
    state: str
    levels_completed: int
    win_levels: int
    available_actions: tuple[int, ...]
    frame: tuple[tuple[int, ...], ...] = ()
    frame_count: int = 0

    @property
    def terminal(self) -> bool:
        return self.state in {"WIN", "GAME_OVER"}

    def snapshot(self) -> JsonDict:
        """Return the deterministic state used by models and prediction checks."""
        return {
            "game_id": self.game_id,
            "state": self.state,
            "levels_completed": self.levels_completed,
            "win_levels": self.win_levels,
            "available_actions": list(self.available_actions),
            "frame_rle": frame_to_rle(self.frame),
        }

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json(self.snapshot()).encode()).hexdigest()

    def to_dict(self) -> JsonDict:
        value = self.snapshot()
        value["frame_count"] = self.frame_count
        value["fingerprint"] = self.fingerprint
        return value


@dataclass(frozen=True)
class Transition:
    before: Observation
    action: Action
    after: Observation

    def delta(self) -> FrameDelta:
        meta = metadata_delta(self.before.snapshot(), self.after.snapshot())
        try:
            frame_delta = compute_frame_delta(self.before.frame, self.after.frame)
        except ValueError:
            # Geometry changed (rare / malformed post-terminal obs). Keep journaling
            # alive: full before/after snapshots are already stored on the Transition.
            return FrameDelta(
                changed_rows=(),
                bbox=None,
                metadata={
                    **meta,
                    "frame_geometry_changed": True,
                    "before_height": len(self.before.frame),
                    "after_height": len(self.after.frame),
                },
            )
        return FrameDelta(
            changed_rows=frame_delta.changed_rows,
            bbox=frame_delta.bbox,
            metadata=meta,
        )

    def to_dict(self) -> JsonDict:
        return {
            "before": self.before.to_dict(),
            "action": asdict(self.action),
            "after": self.after.to_dict(),
            "delta": self.delta().to_dict(),
        }


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_prompt_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.cached_prompt_tokens += other.cached_prompt_tokens
        self.total_tokens += other.total_tokens
        if other.estimated_cost_usd is not None:
            self.estimated_cost_usd = (self.estimated_cost_usd or 0.0) + other.estimated_cost_usd


@dataclass
class RunMetrics:
    agent: str
    game_id: str
    run_index: int
    seed: int
    status: str = "running"
    score: float = 0.0
    levels_completed: int = 0
    win_levels: int = 0
    completed: bool = False
    environment_actions: int = 0
    exploration_actions: int = 0
    planned_actions: int = 0
    fallback_actions: int = 0
    model_calls: int = 0
    model_api_attempts: int = 0
    model_failures: int = 0
    backtest_failures: int = 0
    prediction_mismatches: int = 0
    game_over_resets: int = 0
    usage: Usage = field(default_factory=Usage)
    wall_clock_seconds: float = 0.0
    error: str | None = None
    paired_valid: bool | None = None
    paired_invalid_reason: str | None = None

    def to_dict(self) -> JsonDict:
        return asdict(self)
