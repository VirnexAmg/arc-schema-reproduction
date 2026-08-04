from __future__ import annotations

"""
可执行程序世界模型：把沙箱中的机制程序接到预测、回测与规划。

支持两种兼容接口：

1. legacy：``step(GridState, action) -> GridState`` / ``is_goal(GridState)``；
2. schema：``init_state(entry_grid) -> latent``，
   ``predict(latent, grid, action) -> (next_grid, events, next_latent)``，
   ``is_goal(latent, grid)``。

schema 接口把不可见的机制状态和画面分开，并允许用 LEVEL_COMPLETE / GAME_OVER /
WIN 事件表达边界。关卡切换时只核验事件，不要求模型臆造尚未观察到的下一关整帧。

阅读导引（信任边界核心）：
- ProgramWorldModel：加载并调用沙箱内 WM
- prediction_match_quality：动作前/回测比对（关卡边界严格，像素可 approximate）
- backtest_program：全 Timeline 历史回放认证
- bfs_program_plan：在已认证模型内搜索到达 is_goal 的路径（需 exact）
"""

import ast
import re
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from arc_schema.core import (
    Action,
    Observation,
    Transition,
    canonical_json,
    compute_frame_delta,
)
from arc_schema.planner import PlannedStep
from arc_schema.sandbox import SandboxError, exec_world_model, run_with_timeout


JsonDict = dict[str, Any]

LEVEL_EVENTS = frozenset({"LEVEL_COMPLETE", "LEVEL_COMPLETED", "LEVEL_UP"})
_RLE_LITERAL_PATTERN = re.compile(r"(?:^|[,;\s])\d+:\d+(?=$|[,;\s])")
MAX_RLE_LITERAL_RUNS = 96
MAX_NUMERIC_LITERALS = 512
MAX_SOURCE_LINES = 1_200
MAX_AST_NODES = 20_000
MAX_BRANCH_NODES = 800
HARD_MAX_SOURCE_LINES = 5_000
HARD_MAX_AST_NODES = 100_000
HARD_MAX_BRANCH_NODES = 5_000
MAX_APPROXIMATE_CHANGED_CELLS = 32
MAX_APPROXIMATE_CHANGED_FRACTION = 0.01


@dataclass
class GridState:
    """沙箱内 step()/is_goal() 使用的可变网格状态。"""

    frame: list[list[int]]
    levels_completed: int
    state: str
    available_actions: list[int]
    win_levels: int = 1
    game_id: str = "toy"

    def copy(self) -> GridState:
        return GridState(
            frame=[row[:] for row in self.frame],
            levels_completed=int(self.levels_completed),
            state=str(self.state),
            available_actions=list(self.available_actions),
            win_levels=int(self.win_levels),
            game_id=str(self.game_id),
        )

    def to_snapshot(self) -> JsonDict:
        return {
            "game_id": self.game_id,
            "state": self.state,
            "levels_completed": int(self.levels_completed),
            "win_levels": int(self.win_levels),
            "available_actions": list(self.available_actions),
            "frame_rle": [_row_to_rle(row) for row in self.frame],
        }

    def fingerprint(self) -> str:
        import hashlib

        return hashlib.sha256(canonical_json(self.to_snapshot()).encode()).hexdigest()


def _row_to_rle(row: list[int]) -> str:
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


def observation_to_grid(observation: Observation) -> GridState:
    return GridState(
        frame=[list(row) for row in observation.frame],
        levels_completed=observation.levels_completed,
        state=observation.state,
        available_actions=list(observation.available_actions),
        win_levels=observation.win_levels,
        game_id=observation.game_id,
    )


def grid_to_observation(grid: GridState, *, frame_count: int = 0) -> Observation:
    frame = tuple(tuple(int(cell) for cell in row) for row in grid.frame)
    return Observation(
        game_id=str(grid.game_id),
        state=str(grid.state),
        levels_completed=int(grid.levels_completed),
        win_levels=int(grid.win_levels),
        available_actions=tuple(int(item) for item in grid.available_actions),
        frame=frame,
        frame_count=frame_count,
    )


def find_color(frame: list[list[int]], color: int) -> list[tuple[int, int]]:
    hits: list[tuple[int, int]] = []
    for y, row in enumerate(frame):
        for x, cell in enumerate(row):
            if int(cell) == int(color):
                hits.append((y, x))
    return hits


def bbox(coords: list[tuple[int, int]]) -> tuple[int, int, int, int] | None:
    if not coords:
        return None
    ys = [y for y, _ in coords]
    xs = [x for _, x in coords]
    return min(ys), min(xs), max(ys), max(xs)


def neighbors4(y: int, x: int) -> list[tuple[int, int]]:
    return [(y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)]


def crop_frame(
    frame: list[list[int]],
    bounds: tuple[int, int, int, int],
) -> list[list[int]]:
    """Inclusive y0/x0/y1/x1 crop, available to model-authored code."""
    y0, x0, y1, x1 = (int(value) for value in bounds)
    return [row[x0 : x1 + 1] for row in frame[y0 : y1 + 1]]


def rotate90(frame: list[list[int]], clockwise: bool = True) -> list[list[int]]:
    """Generic quarter-turn helper; it does not encode any game-specific rule."""
    if not frame:
        return []
    if clockwise:
        return [list(row) for row in zip(*frame[::-1], strict=True)]
    return [list(row) for row in zip(*frame, strict=True)][::-1]


def connected_components(
    frame: list[list[int]],
    *,
    background: int | None = None,
) -> list[dict[str, Any]]:
    """Return 4-connected same-colour components for generic visual grounding."""
    seen: set[tuple[int, int]] = set()
    output: list[dict[str, Any]] = []
    height = len(frame)
    width = len(frame[0]) if frame else 0
    for y in range(height):
        for x in range(width):
            color = int(frame[y][x])
            if (y, x) in seen or (background is not None and color == int(background)):
                continue
            stack = [(y, x)]
            seen.add((y, x))
            cells: list[tuple[int, int]] = []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for ny, nx in neighbors4(cy, cx):
                    if not (0 <= ny < height and 0 <= nx < width):
                        continue
                    if (ny, nx) in seen or int(frame[ny][nx]) != color:
                        continue
                    seen.add((ny, nx))
                    stack.append((ny, nx))
            output.append(
                {
                    "color": color,
                    "cells": cells,
                    "bbox": bbox(cells),
                    "size": len(cells),
                }
            )
    return output


def world_model_complexity(source: str) -> dict[str, int]:
    """Return auditable, game-agnostic source-complexity measurements."""
    try:
        tree = ast.parse(source, filename="world_model.py", mode="exec")
    except SyntaxError:
        return {
            "source_lines": len(source.splitlines()),
            "ast_nodes": 0,
            "branch_nodes": 0,
            "numeric_literals": 0,
            "rle_literal_runs": 0,
        }
    numeric_literals = 0
    rle_literal_runs = 0
    branch_nodes = 0
    nodes = list(ast.walk(tree))
    branch_types = (ast.If, ast.For, ast.While, ast.Try, ast.Match, ast.BoolOp)
    for node in nodes:
        if isinstance(node, branch_types):
            branch_nodes += 1
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                numeric_literals += 1
            elif isinstance(node.value, str):
                rle_literal_runs += len(_RLE_LITERAL_PATTERN.findall(node.value))
    return {
        "source_lines": len(source.splitlines()),
        "ast_nodes": len(nodes),
        "branch_nodes": branch_nodes,
        "numeric_literals": numeric_literals,
        "rle_literal_runs": rle_literal_runs,
    }


def audit_world_model_source(source: str) -> list[str]:
    """Hard-reject only extreme structural growth.

    Learned coordinates, colours and compact grid constants are legitimate
    executable theory state. They remain auditable complexity signals, not
    correctness blockers.
    """
    try:
        ast.parse(source, filename="world_model.py", mode="exec")
    except SyntaxError:
        # The sandbox will return the more useful syntax error.
        return []
    complexity = world_model_complexity(source)
    blockers = []
    if complexity["source_lines"] > HARD_MAX_SOURCE_LINES:
        blockers.append(
            f"{complexity['source_lines']} source lines (hard limit {HARD_MAX_SOURCE_LINES})"
        )
    if complexity["ast_nodes"] > HARD_MAX_AST_NODES:
        blockers.append(f"{complexity['ast_nodes']} AST nodes (hard limit {HARD_MAX_AST_NODES})")
    if complexity["branch_nodes"] > HARD_MAX_BRANCH_NODES:
        blockers.append(
            f"{complexity['branch_nodes']} branch nodes (hard limit {HARD_MAX_BRANCH_NODES})"
        )
    return blockers


def world_model_complexity_warnings(source: str) -> list[str]:
    """Soft MDL guidance; warnings never prevent using a predictive model."""
    complexity = world_model_complexity(source)
    warnings: list[str] = []
    if complexity["source_lines"] > MAX_SOURCE_LINES:
        warnings.append(
            f"{complexity['source_lines']} source lines exceed soft target {MAX_SOURCE_LINES}"
        )
    if complexity["ast_nodes"] > MAX_AST_NODES:
        warnings.append(f"{complexity['ast_nodes']} AST nodes exceed soft target {MAX_AST_NODES}")
    if complexity["branch_nodes"] > MAX_BRANCH_NODES:
        warnings.append(
            f"{complexity['branch_nodes']} branch nodes exceed soft target {MAX_BRANCH_NODES}"
        )
    if complexity["rle_literal_runs"] > MAX_RLE_LITERAL_RUNS:
        warnings.append(
            f"{complexity['rle_literal_runs']} embedded RLE runs; review for "
            "trajectory memorisation"
        )
    if complexity["numeric_literals"] > MAX_NUMERIC_LITERALS:
        warnings.append(
            f"{complexity['numeric_literals']} numeric literals; review whether "
            "they encode reusable state or one trajectory"
        )
    return warnings


SANDBOX_HELPERS: dict[str, Any] = {
    "GridState": GridState,
    "find_color": find_color,
    "bbox": bbox,
    "neighbors4": neighbors4,
    "crop_frame": crop_frame,
    "rotate90": rotate90,
    "connected_components": connected_components,
    "deepcopy": deepcopy,
    "np": np,
}


@dataclass(frozen=True)
class ProgramBacktestResult:
    passed: bool
    checked: int
    mismatch_index: int | None = None
    reason: str | None = None
    predicted: JsonDict | None = None
    actual: JsonDict | None = None
    approximate_matches: int = 0
    checked_by_action: JsonDict = field(default_factory=dict)


@dataclass
class ProgramRuntimeState:
    """Host-side node used to carry a model's latent state through replay/BFS."""

    observation: Observation
    latent: Any = None

    @property
    def fingerprint(self) -> str:
        try:
            latent = canonical_json(self.latent)
        except (TypeError, ValueError):
            latent = repr(self.latent)
        return f"{self.observation.fingerprint}:{latent}"


@dataclass
class ProgramPrediction:
    """A pre-action prediction plus its next runtime node."""

    before: Observation
    action: Action
    observation: Observation
    events: tuple[str, ...]
    next_runtime: ProgramRuntimeState
    interface: str


@dataclass(frozen=True)
class PredictionMatchResult:
    """Whether a prediction is useful enough to continue acting."""

    matched: bool
    exact: bool
    critical: bool
    reason: str
    differing_cells: int = 0
    total_cells: int = 0


def _event_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().upper()
    if isinstance(value, dict):
        for key in ("event", "type", "name"):
            if key in value:
                return str(value[key]).strip().upper()
    return str(value).strip().upper()


def _normalise_events(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    items = value if isinstance(value, (list, tuple)) else [value]
    return tuple(name for name in (_event_name(item) for item in items) if name)


def _frame_tuple(value: Any) -> tuple[tuple[int, ...], ...]:
    if isinstance(value, GridState):
        value = value.frame
    if not isinstance(value, (list, tuple)):
        raise SandboxError("predict() next_grid must be a rectangular grid or GridState")
    rows = tuple(tuple(int(cell) for cell in row) for row in value)
    if rows:
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise SandboxError("predict() next_grid rows must have equal width")
    return rows


def prediction_indicates_progress(prediction: ProgramPrediction) -> bool:
    event_names = set(prediction.events)
    return (
        bool(event_names & LEVEL_EVENTS)
        or "WIN" in event_names
        or prediction.observation.state == "WIN"
        or prediction.observation.levels_completed > prediction.before.levels_completed
    )


def prediction_match_quality(
    prediction: ProgramPrediction,
    actual: Observation,
    *,
    allow_approximate: bool = False,
) -> PredictionMatchResult:
    """比对预测与真实：level/WIN/GAME_OVER/动作空间严格；非终局小像素误差可近似通过。"""
    names = set(prediction.events)
    predicted_level = bool(names & LEVEL_EVENTS) or (
        prediction.observation.levels_completed > prediction.before.levels_completed
    )
    actual_level = actual.levels_completed > prediction.before.levels_completed
    if predicted_level != actual_level:
        return PredictionMatchResult(False, False, True, "level progress mismatch")
    predicted_game_over = "GAME_OVER" in names or prediction.observation.state == "GAME_OVER"
    if predicted_game_over != (actual.state == "GAME_OVER"):
        return PredictionMatchResult(False, False, True, "GAME_OVER mismatch")
    predicted_win = "WIN" in names or prediction.observation.state == "WIN"
    if predicted_win != (actual.state == "WIN"):
        return PredictionMatchResult(False, False, True, "WIN mismatch")
    if actual_level:
        # The next level's entry frame is supplied by the environment and becomes
        # a fresh init_state() input; the model only predicts the boundary event.
        return PredictionMatchResult(True, True, True, "level boundary matched")
    if prediction.observation.levels_completed != actual.levels_completed:
        return PredictionMatchResult(False, False, True, "level metadata mismatch")
    if prediction.observation.state != actual.state:
        return PredictionMatchResult(False, False, True, "state mismatch")
    if prediction.observation.available_actions != actual.available_actions:
        return PredictionMatchResult(False, False, True, "available actions mismatch")
    predicted_frame = prediction.observation.frame
    actual_frame = actual.frame
    if len(predicted_frame) != len(actual_frame) or any(
        len(predicted_row) != len(actual_row)
        for predicted_row, actual_row in zip(
            predicted_frame,
            actual_frame,
            strict=False,
        )
    ):
        return PredictionMatchResult(False, False, True, "frame shape mismatch")
    total_cells = sum(len(row) for row in actual_frame)
    differing_cells = sum(
        int(predicted_cell != actual_cell)
        for predicted_row, actual_row in zip(
            predicted_frame,
            actual_frame,
            strict=True,
        )
        for predicted_cell, actual_cell in zip(
            predicted_row,
            actual_row,
            strict=True,
        )
    )
    if differing_cells == 0:
        return PredictionMatchResult(
            True,
            True,
            False,
            "exact frame match",
            0,
            total_cells,
        )
    fraction = differing_cells / max(total_cells, 1)
    if (
        allow_approximate
        and differing_cells <= MAX_APPROXIMATE_CHANGED_CELLS
        and fraction <= MAX_APPROXIMATE_CHANGED_FRACTION
    ):
        return PredictionMatchResult(
            True,
            False,
            False,
            "small non-terminal visual mismatch",
            differing_cells,
            total_cells,
        )
    return PredictionMatchResult(
        False,
        False,
        False,
        "frame mismatch exceeds instrumental tolerance",
        differing_cells,
        total_cells,
    )


def prediction_matches(prediction: ProgramPrediction, actual: Observation) -> bool:
    """Backward-compatible boolean wrapper around prediction_match_quality."""
    return prediction_match_quality(prediction, actual).matched


def _observation_summary(observation: Observation) -> JsonDict:
    return {
        "fingerprint": observation.fingerprint,
        "state": observation.state,
        "levels_completed": observation.levels_completed,
        "available_actions": list(observation.available_actions),
        "frame_shape": [
            len(observation.frame),
            len(observation.frame[0]) if observation.frame else 0,
        ],
    }


def prediction_mismatch_summary(
    prediction: ProgramPrediction,
    actual: Observation,
) -> tuple[JsonDict, JsonDict]:
    """Compact mismatch feedback; full snapshots remain in the Transition journal."""
    predicted = _observation_summary(prediction.observation)
    predicted["events"] = list(prediction.events)
    actual_summary = _observation_summary(actual)
    try:
        delta = compute_frame_delta(prediction.observation.frame, actual.frame)
        actual_summary["prediction_delta"] = delta.to_dict()
    except ValueError:
        actual_summary["prediction_delta"] = {
            "metadata": {"frame_geometry_changed": True},
            "rows": [],
        }
    return predicted, actual_summary


class ProgramWorldModel:
    """从沙箱源码加载的可执行世界模型，兼容 legacy 与 schema 接口。"""

    def __init__(
        self,
        source: str,
        *,
        step_timeout_seconds: float = 0.25,
        load_timeout_seconds: float = 2.0,
    ) -> None:
        self.source = source
        blockers = audit_world_model_source(source)
        if blockers:
            raise SandboxError(
                "world model static audit rejected memorisation or over-complex source: "
                + "; ".join(blockers)
                + ". Encode reusable objects/mechanisms instead."
            )
        namespace = exec_world_model(
            source,
            helpers=SANDBOX_HELPERS,
            timeout_seconds=load_timeout_seconds,
        )
        step = namespace.get("step")
        predict = namespace.get("predict")
        init_state = namespace.get("init_state")
        is_goal = namespace.get("is_goal")
        if not callable(is_goal):
            raise SandboxError("world_model.py must define callable is_goal")
        if callable(predict):
            if not callable(init_state):
                raise SandboxError(
                    "schema predict() interface requires callable init_state(entry_grid)"
                )
            self.interface = "schema"
        elif callable(step):
            self.interface = "legacy"
        else:
            raise SandboxError(
                "world_model.py must define step(state, action), or init_state()+predict()"
            )
        self._step: Callable[..., Any] | None = step if callable(step) else None
        self._predict: Callable[..., Any] | None = predict if callable(predict) else None
        self._init_state: Callable[..., Any] | None = init_state if callable(init_state) else None
        self._is_goal: Callable[..., Any] = is_goal
        self.step_timeout_seconds = step_timeout_seconds

    def _sandbox_call(self, fn: Callable[[], Any], label: str) -> Any:
        try:
            return run_with_timeout(fn, timeout_seconds=self.step_timeout_seconds)
        except TimeoutError as exc:
            raise SandboxError(str(exc)) from exc
        except SandboxError:
            raise
        except Exception as exc:
            raise SandboxError(f"{label} raised {type(exc).__name__}: {exc}") from exc

    def start_runtime(self, observation: Observation) -> ProgramRuntimeState:
        if self.interface == "legacy":
            return ProgramRuntimeState(observation, None)
        entry_grid = [list(row) for row in observation.frame]

        def _call() -> Any:
            assert self._init_state is not None
            return self._init_state(entry_grid)

        latent = self._sandbox_call(_call, "init_state()")
        return ProgramRuntimeState(observation, deepcopy(latent))

    def predict_runtime(
        self,
        runtime: ProgramRuntimeState,
        action: Action,
    ) -> ProgramPrediction:
        observation = runtime.observation
        action_payload = {"id": int(action.id), "data": dict(action.data)}
        if self.interface == "legacy":
            state = observation_to_grid(observation)

            def _call_legacy() -> Any:
                assert self._step is not None
                return self._step(state, action_payload)

            result = self._sandbox_call(_call_legacy, "step()")
            if not isinstance(result, GridState):
                raise SandboxError("step() must return a GridState")
            predicted = grid_to_observation(
                result,
                frame_count=observation.frame_count + 1,
            )
            next_runtime = ProgramRuntimeState(predicted, None)
            return ProgramPrediction(
                observation,
                action,
                predicted,
                (),
                next_runtime,
                self.interface,
            )

        grid = [list(row) for row in observation.frame]
        latent = deepcopy(runtime.latent)

        def _call_schema() -> Any:
            assert self._predict is not None
            return self._predict(latent, grid, action_payload)

        result = self._sandbox_call(_call_schema, "predict()")
        if not isinstance(result, (list, tuple)) or len(result) != 3:
            raise SandboxError("predict() must return (next_grid, events, next_latent)")
        next_grid, raw_events, next_latent = result
        frame = _frame_tuple(next_grid)
        events = _normalise_events(raw_events)
        names = set(events)
        levels = observation.levels_completed + int(bool(names & LEVEL_EVENTS))
        state = observation.state
        if "GAME_OVER" in names:
            state = "GAME_OVER"
        elif "WIN" in names:
            state = "WIN"
        predicted = Observation(
            game_id=observation.game_id,
            state=state,
            levels_completed=levels,
            win_levels=observation.win_levels,
            available_actions=observation.available_actions,
            frame=frame,
            frame_count=observation.frame_count + 1,
        )
        next_runtime = ProgramRuntimeState(predicted, deepcopy(next_latent))
        return ProgramPrediction(
            observation,
            action,
            predicted,
            events,
            next_runtime,
            self.interface,
        )

    def predict(self, observation: Observation, action: Action) -> Observation:
        """Backward-compatible stateless convenience wrapper."""
        runtime = self.start_runtime(observation)
        return self.predict_runtime(runtime, action).observation

    def accept_actual(
        self,
        prediction: ProgramPrediction,
        actual: Observation,
    ) -> ProgramRuntimeState:
        if actual.state in {"GAME_OVER", "WIN", "NOT_PLAYED"}:
            return ProgramRuntimeState(actual, None)
        if actual.levels_completed > prediction.before.levels_completed:
            return self.start_runtime(actual)
        return ProgramRuntimeState(actual, deepcopy(prediction.next_runtime.latent))

    def runtime_from_history(
        self,
        current: Observation,
        history: list[Transition],
    ) -> ProgramRuntimeState:
        """Replay the current life/level to reconstruct latent state."""
        runtime: ProgramRuntimeState | None = None
        for transition in history:
            if _is_skippable_backtest_transition(transition):
                runtime = None
                continue
            if runtime is None or runtime.observation.fingerprint != transition.before.fingerprint:
                runtime = self.start_runtime(transition.before)
            prediction = self.predict_runtime(runtime, transition.action)
            runtime = self.accept_actual(prediction, transition.after)
        if runtime is None or runtime.observation.fingerprint != current.fingerprint:
            return self.start_runtime(current)
        return runtime

    def is_goal_runtime(self, runtime: ProgramRuntimeState) -> bool:
        if self.interface == "legacy":
            state = observation_to_grid(runtime.observation)

            def _call_legacy() -> Any:
                return self._is_goal(state)

            return bool(self._sandbox_call(_call_legacy, "is_goal()"))
        latent = deepcopy(runtime.latent)
        grid = [list(row) for row in runtime.observation.frame]

        def _call_schema() -> Any:
            return self._is_goal(latent, grid)

        return bool(self._sandbox_call(_call_schema, "is_goal()"))

    def is_goal(self, observation: Observation) -> bool:
        return self.is_goal_runtime(self.start_runtime(observation))


def _is_skippable_backtest_transition(transition: Transition) -> bool:
    """Schema-style: skip RESET and other non-gameplay terminal bookkeeping steps."""
    if transition.action.id == 0:
        return True
    if transition.before.state in {"GAME_OVER", "WIN", "NOT_PLAYED"}:
        return True
    return False


def backtest_program(
    model: ProgramWorldModel,
    history: list[Transition],
    *,
    allow_approximate: bool = False,
) -> ProgramBacktestResult:
    """全 Timeline 回放：任一步预测不符即失败；RESET 等可跳过转移不计入 checked。"""
    checked = 0
    approximate_matches = 0
    checked_by_action: dict[str, int] = {}
    runtime: ProgramRuntimeState | None = None
    for index, transition in enumerate(history):
        if _is_skippable_backtest_transition(transition):
            runtime = None
            continue
        checked += 1
        action_key = str(transition.action.id)
        checked_by_action[action_key] = checked_by_action.get(action_key, 0) + 1
        try:
            if runtime is None or runtime.observation.fingerprint != transition.before.fingerprint:
                runtime = model.start_runtime(transition.before)
            prediction = model.predict_runtime(runtime, transition.action)
        except SandboxError as exc:
            return ProgramBacktestResult(
                False,
                checked,
                index,
                f"prediction error: {exc}",
                actual=_observation_summary(transition.after),
                approximate_matches=approximate_matches,
                checked_by_action=dict(checked_by_action),
            )
        match = prediction_match_quality(
            prediction,
            transition.after,
            allow_approximate=allow_approximate,
        )
        if not match.matched:
            predicted, actual = prediction_mismatch_summary(
                prediction,
                transition.after,
            )
            return ProgramBacktestResult(
                False,
                checked,
                index,
                "predicted state differs from historical observation",
                predicted=predicted,
                actual=actual,
                approximate_matches=approximate_matches,
                checked_by_action=dict(checked_by_action),
            )
        if not match.exact:
            approximate_matches += 1
        runtime = model.accept_actual(prediction, transition.after)
    return ProgramBacktestResult(
        True,
        checked,
        approximate_matches=approximate_matches,
        checked_by_action=dict(checked_by_action),
    )


def bfs_program_plan(
    model: ProgramWorldModel,
    start: Observation,
    *,
    max_nodes: int,
    max_depth: int | None = None,
    legal_action_ids: tuple[int, ...] | None = None,
    history: list[Transition] | None = None,
) -> list[PlannedStep] | None:
    """在已认证的程序世界模型内 BFS，搜索到达 is_goal 的动作路径。"""
    fallback_action_ids = legal_action_ids or start.available_actions
    start_runtime = model.runtime_from_history(start, history or [])
    queue: deque[tuple[ProgramRuntimeState, list[PlannedStep]]] = deque([(start_runtime, [])])
    visited = {start_runtime.fingerprint}
    expanded = 0
    while queue and expanded < max_nodes:
        runtime, path = queue.popleft()
        expanded += 1
        try:
            if model.is_goal_runtime(runtime):
                return path
        except SandboxError:
            continue
        if max_depth is not None and len(path) >= max_depth:
            continue
        action_ids = runtime.observation.available_actions or fallback_action_ids
        for action_id in action_ids:
            if action_id in {0, 6}:
                continue
            action = Action(id=int(action_id))
            try:
                prediction = model.predict_runtime(runtime, action)
            except SandboxError:
                continue
            nxt = prediction.next_runtime
            fingerprint = nxt.fingerprint
            if fingerprint in visited:
                continue
            visited.add(fingerprint)
            next_path = [*path, PlannedStep(action, fingerprint)]
            if prediction_indicates_progress(prediction):
                return next_path
            queue.append((nxt, next_path))
    return None


DEFAULT_WORLD_MODEL_STUB = '''\
# World model stub. Prefer the latent/event API for new theories:
#   init_state(entry_grid)
#   predict(latent, grid, action) -> (next_grid, events, next_latent)
#   is_goal(latent, grid)
# Legacy step(GridState, action) remains supported.
# Generic helpers: GridState, find_color, bbox, neighbors4, crop_frame,
# rotate90, connected_components, deepcopy.

def step(state, action):
    """Return next GridState. Must not invent levels without evidence."""
    nxt = state.copy()
    # Default: identity transition (safe but not useful for planning).
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
'''
