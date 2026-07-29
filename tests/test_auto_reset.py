from __future__ import annotations

from dataclasses import replace

from arc_schema.agents import BaselineAgent
from arc_schema.config import ExperimentConfig, ModelConfig
from arc_schema.core import Action, Transition
from arc_schema.mock import ToyEnvironment, toy_observation
from arc_schema.program_world_model import backtest_program, ProgramWorldModel
from arc_schema.runner import run_agent


def _cfg(**kwargs) -> ExperimentConfig:
    base = ExperimentConfig(
        game_id="toy",
        max_environment_actions=6,
        run_timeout_seconds=60.0,
        max_model_calls_per_run=20,
        auto_reset_on_game_over=True,
        max_game_over_resets=3,
        harness_mode="schema",
        model=ModelConfig(model="mock"),
    )
    return replace(base, **kwargs)


class AlwaysAction2:
    """Baseline client stand-in: choose action 2 (lethal in lethal toy)."""

    def choose_action(self, current, history, journal, metrics):
        del history, journal, metrics
        if 2 in current.available_actions:
            return Action(id=2)
        return Action(id=current.available_actions[0])


def test_backtest_skips_reset_transitions() -> None:
    model = ProgramWorldModel(
        '''
def step(state, action):
    return state.copy()
def is_goal(state):
    return False
'''
    )
    before = toy_observation(0, state="GAME_OVER")
    after = toy_observation(0)
    history = [Transition(before, Action(id=0), after)]
    result = backtest_program(model, history)
    assert result.passed
    assert result.checked == 0


def test_auto_reset_on_game_over_preserves_budget(tmp_path) -> None:
    environment = ToyEnvironment(lethal_action=2)
    # Monkeypatch BaselineAgent protocol via duck typing in run_agent — use real BaselineAgent
    # with a tiny wrapper client is heavy; call helper path via BaselineAgent subclassing name.

    class LethalBaseline(BaselineAgent):
        name = "baseline"

        def __init__(self) -> None:
            self.client = None  # type: ignore[assignment]
            self.config = _cfg()

        def choose_action(self, current, history, journal, metrics):
            del history, journal, metrics
            if 2 in current.available_actions:
                return Action(id=2)
            return Action(id=int(current.available_actions[0]))

    metrics = run_agent(
        LethalBaseline(),
        environment,
        _cfg(max_environment_actions=5, max_game_over_resets=2),
        run_index=0,
        seed=0,
        journal_path=tmp_path / "reset.jsonl",
    )
    assert environment.resets >= 1
    assert metrics.game_over_resets >= 1
    assert metrics.environment_actions == 5
    # Should not die permanently on first GAME_OVER when resets remain.
    assert metrics.status in {"action_budget_exhausted", "game_over"}
