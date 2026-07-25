from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from arc_schema.core import Action, Observation


class Environment(Protocol):
    @property
    def current(self) -> Observation: ...

    def step(self, action: Action) -> Observation: ...

    def score_summary(self) -> dict[str, Any]: ...


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def normalize_arc_observation(raw: Any) -> Observation:
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
        legal = set(self._current.available_actions)
        if action.id == 0 or self._current.state in {"GAME_OVER", "WIN", "NOT_PLAYED"}:
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
