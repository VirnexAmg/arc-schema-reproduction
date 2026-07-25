from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arc_schema.core import Transition, canonical_json
from arc_schema.world_model import DeclarativeWorldModel


@dataclass(frozen=True)
class BacktestResult:
    passed: bool
    checked: int
    mismatch_index: int | None = None
    reason: str | None = None
    predicted: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None


def backtest(
    model: DeclarativeWorldModel,
    history: list[Transition],
    *,
    limit: int | None = None,
) -> BacktestResult:
    """Replay history through the world model.

    When ``limit`` is set, only the trailing window is checked. This must match
    the compact context / catalog window shown to the model.
    """
    window = history if limit is None else history[-limit:]
    for index, transition in enumerate(window):
        source = model.state_for_observation(transition.before)
        if source is None:
            return BacktestResult(
                False,
                index,
                index,
                "before observation is absent from world model",
                actual=transition.before.snapshot(),
            )
        predicted = model.predict(source, transition.action)
        if predicted is None:
            return BacktestResult(
                False,
                index,
                index,
                "historical transition is absent from world model",
                actual=transition.after.snapshot(),
            )
        actual = transition.after.snapshot()
        if canonical_json(predicted.snapshot) != canonical_json(actual):
            return BacktestResult(
                False,
                index,
                index,
                "predicted state differs from historical observation",
                predicted=predicted.snapshot,
                actual=actual,
            )
    return BacktestResult(True, len(window))
