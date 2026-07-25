from __future__ import annotations

"""
可执行程序世界模型：把沙箱中的 step()/is_goal() 接到预测、回测与规划。

与声明式 DeclarativeWorldModel（状态图 JSON）不同，本模块面向 LLM 生成的 Python 源码：
1. 通过 sandbox.exec_world_model 加载源码，并注入 SANDBOX_HELPERS（GridState、找色、包围盒等）；
2. ProgramWorldModel 校验并包装 step/is_goal，在超时保护下做单步预测与目标判定；
3. backtest_program 用历史 Transition 检验预测是否与真实观察一致；
4. bfs_program_plan 在已认证模型内 BFS 搜索到达 is_goal 的动作序列。

GridState 是暴露给沙箱代码的可变网格状态；Observation 与 GridState 通过互转函数衔接宿主与模型。
DEFAULT_WORLD_MODEL_STUB 为初始占位实现（恒等 step），供 workspace 等作为改写起点。
"""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from arc_schema.core import Action, Observation, Transition, canonical_json
from arc_schema.planner import PlannedStep
from arc_schema.sandbox import SandboxError, exec_world_model, run_with_timeout


JsonDict = dict[str, Any]


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


SANDBOX_HELPERS: dict[str, Any] = {
    "GridState": GridState,
    "find_color": find_color,
    "bbox": bbox,
    "neighbors4": neighbors4,
    "deepcopy": deepcopy,
}


@dataclass(frozen=True)
class ProgramBacktestResult:
    passed: bool
    checked: int
    mismatch_index: int | None = None
    reason: str | None = None
    predicted: JsonDict | None = None
    actual: JsonDict | None = None


class ProgramWorldModel:
    """从沙箱源码加载的可执行 Schema 风格世界模型（包装 step / is_goal）。"""

    def __init__(
        self,
        source: str,
        *,
        step_timeout_seconds: float = 0.25,
        load_timeout_seconds: float = 2.0,
    ) -> None:
        self.source = source
        namespace = exec_world_model(
            source,
            helpers=SANDBOX_HELPERS,
            timeout_seconds=load_timeout_seconds,
        )
        step = namespace.get("step")
        is_goal = namespace.get("is_goal")
        if not callable(step):
            raise SandboxError("world_model.py must define callable step(state, action)")
        if not callable(is_goal):
            raise SandboxError("world_model.py must define callable is_goal(state)")
        self._step: Callable[..., Any] = step
        self._is_goal: Callable[..., Any] = is_goal
        self.step_timeout_seconds = step_timeout_seconds

    def predict(self, observation: Observation, action: Action) -> Observation:
        state = observation_to_grid(observation)
        action_payload = {"id": int(action.id), "data": dict(action.data)}

        def _call() -> Any:
            return self._step(state, action_payload)

        try:
            result = run_with_timeout(_call, timeout_seconds=self.step_timeout_seconds)
        except TimeoutError as exc:
            raise SandboxError(str(exc)) from exc
        except SandboxError:
            raise
        except Exception as exc:
            raise SandboxError(f"step() raised {type(exc).__name__}: {exc}") from exc
        if not isinstance(result, GridState):
            raise SandboxError("step() must return a GridState")
        return grid_to_observation(result, frame_count=observation.frame_count + 1)

    def is_goal(self, observation: Observation) -> bool:
        state = observation_to_grid(observation)

        def _call() -> Any:
            return self._is_goal(state)

        try:
            result = run_with_timeout(_call, timeout_seconds=self.step_timeout_seconds)
        except TimeoutError as exc:
            raise SandboxError(str(exc)) from exc
        except Exception as exc:
            raise SandboxError(f"is_goal() raised {type(exc).__name__}: {exc}") from exc
        return bool(result)


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
) -> ProgramBacktestResult:
    checked = 0
    for index, transition in enumerate(history):
        if _is_skippable_backtest_transition(transition):
            continue
        checked += 1
        try:
            predicted = model.predict(transition.before, transition.action)
        except SandboxError as exc:
            return ProgramBacktestResult(
                False,
                checked,
                index,
                f"step() error: {exc}",
                actual=transition.after.snapshot(),
            )
        actual = transition.after.snapshot()
        if canonical_json(predicted.snapshot()) != canonical_json(actual):
            return ProgramBacktestResult(
                False,
                checked,
                index,
                "predicted state differs from historical observation",
                predicted=predicted.snapshot(),
                actual=actual,
            )
    return ProgramBacktestResult(True, checked)


def bfs_program_plan(
    model: ProgramWorldModel,
    start: Observation,
    *,
    max_nodes: int,
    max_depth: int | None = None,
    legal_action_ids: tuple[int, ...] | None = None,
) -> list[PlannedStep] | None:
    """在已认证的程序世界模型内 BFS，搜索到达 is_goal 的动作路径。"""
    action_ids = legal_action_ids or start.available_actions
    queue: deque[tuple[Observation, list[PlannedStep]]] = deque([(start, [])])
    visited = {start.fingerprint}
    expanded = 0
    while queue and expanded < max_nodes:
        current, path = queue.popleft()
        expanded += 1
        try:
            if model.is_goal(current):
                return path
        except SandboxError:
            continue
        if max_depth is not None and len(path) >= max_depth:
            continue
        for action_id in action_ids:
            if action_id in {0, 6}:
                continue
            action = Action(id=int(action_id))
            try:
                nxt = model.predict(current, action)
            except SandboxError:
                continue
            fingerprint = nxt.fingerprint
            if fingerprint in visited:
                continue
            visited.add(fingerprint)
            queue.append((nxt, [*path, PlannedStep(action, fingerprint)]))
    return None


DEFAULT_WORLD_MODEL_STUB = '''\
# Schema-style world model stub. Replace step/is_goal with real hypotheses.
# Helpers available: GridState, find_color, bbox, neighbors4, deepcopy

def step(state, action):
    """Return next GridState. Must not invent levels without evidence."""
    nxt = state.copy()
    # Default: identity transition (safe but not useful for planning).
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
'''
