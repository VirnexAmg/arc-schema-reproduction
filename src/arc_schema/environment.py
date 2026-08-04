from __future__ import annotations

"""
真实 ARC SDK 适配层：把 arc_agi / arcengine 规范化为本仓库的 Environment 协议。

阅读导引：
- Environment：统一协议（Toy 与真实 ARC 共用）
- normalize_arc_observation：处理 FrameDataRaw | None，抽最后一帧与元数据
- ArcEnvironmentAdapter.step：合法性门禁（终局仅 RESET）并调用 SDK
- ArcEnvironmentFactory.create(seed)：按游戏 id 与环境 seed 建局
"""

from dataclasses import dataclass
from typing import Any, Protocol

from arc_schema.core import Action, Observation


class Environment(Protocol):
    """环境协议：当前观察、步进、scorecard 摘要。"""

    @property
    def current(self) -> Observation: ...

    def step(self, action: Action) -> Observation: ...

    def score_summary(self) -> dict[str, Any]: ...


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def normalize_arc_observation(raw: Any) -> Observation:
    """将 SDK 原始观察转为 Observation；raw 为 None 时立即失败（FrameDataRaw | None）。"""
    if raw is None:
        raise RuntimeError("ARC environment returned no observation")
    frames = list(raw.frame)
    last_frame = frames[-1].tolist() if frames else []
    return Observation(
        game_id=str(raw.game_id),
        state=_enum_value(raw.state),
        levels_completed=int(raw.levels_completed),
        win_levels=int(raw.win_levels),
        available_actions=tuple(int(item) for item in raw.available_actions),
        frame=tuple(tuple(int(cell) for cell in row) for row in last_frame),
        frame_count=len(frames),
    )


class ArcEnvironmentAdapter:
    """ARC SDK 包装器：维护当前 Observation，并统一非法动作/终局 RESET 规则。"""

    def __init__(self, arcade: Any, environment: Any) -> None:
        self._arcade = arcade
        self._environment = environment
        self._current = normalize_arc_observation(environment.observation_space)

    @property
    def current(self) -> Observation:
        return self._current

    def step(self, action: Action) -> Observation:
        from arcengine import GameAction

        # RESET (id=0) is accepted by ARC even when omitted from available_actions,
        # and is required after GAME_OVER / WIN / NOT_PLAYED.
        # After a terminal state, ONLY RESET is legal — ARC may still list ACTION1-4 in
        # available_actions, but stepping them can return malformed / geometry-changing
        # frames and crash journaling (B3: frame heights must match for delta).
        if self._current.state in {"GAME_OVER", "WIN", "NOT_PLAYED"}:
            legal = {0}
        else:
            legal = set(self._current.available_actions)
            legal.add(0)
        if action.id not in legal:
            raise ValueError(f"illegal action {action.id}; legal={sorted(legal)}")
        raw = self._environment.step(GameAction.from_id(action.id), data=action.data)
        self._current = normalize_arc_observation(raw)
        return self._current

    def score_summary(self) -> dict[str, Any]:
        scorecard = self._arcade.get_scorecard()
        dumped = scorecard.model_dump(mode="json")
        game_id = self._current.game_id
        environment = next(
            (item for item in dumped["environments"] if item["id"] == game_id),
            dumped["environments"][-1] if dumped["environments"] else {},
        )
        run = environment.get("runs", [{}])[-1]
        return {
            "score": float(run.get("score", environment.get("score", 0.0))),
            "levels_completed": int(run.get("levels_completed", self._current.levels_completed)),
            "completed": bool(run.get("completed", self._current.state == "WIN")),
        }


@dataclass(frozen=True)
class ArcEnvironmentFactory:
    """按 game_id / operation_mode / seed 创建适配后的 ARC 环境。"""

    game_id: str
    operation_mode: str = "offline"
    render_mode: str | None = None

    def create(self, seed: int) -> ArcEnvironmentAdapter:
        import arc_agi

        try:
            mode = arc_agi.OperationMode(self.operation_mode)
        except ValueError as exc:
            raise ValueError(f"unsupported ARC operation mode: {self.operation_mode}") from exc
        arcade = arc_agi.Arcade(operation_mode=mode)
        environment = arcade.make(
            self.game_id,
            seed=seed,
            render_mode=self.render_mode,
            include_frame_data=True,
        )
        if environment is None:
            raise RuntimeError(f"failed to create ARC environment {self.game_id}")
        return ArcEnvironmentAdapter(arcade, environment)
