from __future__ import annotations

"""
模型上下文组装：观察目录、稀疏历史、PNG 视觉帧。

阅读导引：
- build_compact_context：给审议/Codex 的紧凑 JSON 上下文（受 context_transitions 限制）
- frame_png_bytes / frame_png_base64：当前帧高对比 PNG，供 vision 附件
- untried_actions / next_explore_action：探索动作启发式
注意：给模型的历史窗口可以裁剪；backtest 仍用完整 Timeline。
"""

import base64
import hashlib
import struct
import zlib
from collections import Counter
from typing import Any

from arc_schema.core import Action, Observation, Transition, canonical_json


JsonDict = dict[str, Any]

# 高对比 16 色 ARC 调色板；越界颜色用确定性灰度，避免静默裁成纯黑。
ARC_RGB_PALETTE: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),
    (0, 116, 217),
    (255, 65, 54),
    (46, 204, 64),
    (255, 220, 0),
    (170, 170, 170),
    (240, 18, 190),
    (255, 133, 27),
    (127, 219, 255),
    (135, 12, 37),
    (255, 255, 255),
    (57, 204, 204),
    (177, 13, 201),
    (1, 255, 112),
    (255, 183, 76),
    (80, 80, 80),
)


def observation_regime_key(observation: Observation) -> tuple[Any, ...]:
    """忽略 HUD/meter 像素抖动的抽象局面键，用于探索去重。"""
    return (
        observation.game_id,
        observation.state,
        observation.levels_completed,
        observation.available_actions,
        len(observation.frame),
        len(observation.frame[0]) if observation.frame else 0,
    )


def untried_actions(
    current: Observation,
    history: list[Transition],
) -> list[int]:
    """Return actions not tried in the current level/state/action-space regime."""
    regime = observation_regime_key(current)
    tried = {
        item.action.id
        for item in history
        if observation_regime_key(item.before) == regime and not item.action.data
    }
    return [action_id for action_id in current.available_actions if action_id not in tried]


def next_explore_action(
    current: Observation,
    history: list[Transition],
) -> Action | None:
    """Pick a balanced explore action inside an abstract state regime.

    Exact fingerprints often change every step because of counters/HUD pixels. Using
    them made every state look novel and repeatedly selected the lowest action id.
    This fallback instead balances actions within the current level and action space.
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

    regime = observation_regime_key(current)
    regime_counts: Counter[int] = Counter()
    global_counts: Counter[int] = Counter()
    for item in history:
        if item.action.data:
            continue
        global_counts[item.action.id] += 1
        if observation_regime_key(item.before) == regime:
            regime_counts[item.action.id] += 1
    return Action(
        id=min(
            pool,
            key=lambda action_id: (
                regime_counts[action_id],
                global_counts[action_id],
                action_id,
            ),
        )
    )


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def frame_png_bytes(observation: Observation, *, target_size: int = 512) -> bytes:
    """把网格帧渲成高对比、近邻放大的 RGB PNG 字节（无外部图像库依赖）。"""
    if not observation.frame:
        raise ValueError("observation has no frame")
    height = len(observation.frame)
    width = len(observation.frame[0])
    if any(len(row) != width for row in observation.frame):
        raise ValueError("observation frame must be rectangular")
    scale = max(1, target_size // max(width, height))
    rendered_width = width * scale
    rendered_height = height * scale
    raw = bytearray()
    for row in observation.frame:
        expanded = bytearray()
        for cell in row:
            value = int(cell)
            if 0 <= value < len(ARC_RGB_PALETTE):
                rgb = ARC_RGB_PALETTE[value]
            else:
                gray = value % 256
                rgb = (gray, gray, gray)
            for _ in range(scale):
                expanded.extend(rgb)
        for _ in range(scale):
            raw.append(0)  # filter: None
            raw.extend(expanded)
    compressed = zlib.compress(bytes(raw), level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR",
            struct.pack(
                ">IIBBBBB",
                rendered_width,
                rendered_height,
                8,
                2,  # truecolour RGB
                0,
                0,
                0,
            ),
        )
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def frame_png_base64(observation: Observation) -> str:
    return base64.b64encode(frame_png_bytes(observation)).decode("ascii")


def frame_png_manifest(observation: Observation) -> JsonDict:
    png = frame_png_bytes(observation)
    height = len(observation.frame)
    width = len(observation.frame[0]) if observation.frame else 0
    scale = max(1, 512 // max(width, height))
    return {
        "sha256": hashlib.sha256(png).hexdigest(),
        "original_size": [width, height],
        "rendered_size": [width * scale, height * scale],
        "mode": "rgb_arc_palette_nearest",
    }


def local_observation_catalog(
    current: Observation,
    history: list[Transition],
    *,
    limit: int,
) -> dict[str, JsonDict]:
    """权威本地观察目录：供 snapshot_ref / patch 物化。"""
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
    组装 baseline / harness 共用的紧凑上下文。

    当前观察始终含完整 frame_rle；历史只用稀疏 delta。
    返回 (payload, vision_parts)；vision 关闭时 vision_parts 为 None。
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
        payload["vision_frame"] = frame_png_manifest(current)
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
