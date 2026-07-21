from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from arc_schema.core import Action
from arc_schema.world_model import DeclarativeWorldModel


@dataclass(frozen=True)
class PlannedStep:
    action: Action
    predicted_state_id: str


def bfs_plan(
    model: DeclarativeWorldModel,
    start_state_id: str,
    max_nodes: int,
    *,
    max_depth: int | None = None,
) -> list[PlannedStep] | None:
    queue: deque[tuple[str, list[PlannedStep]]] = deque([(start_state_id, [])])
    visited = {start_state_id}
    expanded = 0
    while queue and expanded < max_nodes:
        state_id, path = queue.popleft()
        expanded += 1
        if model.is_goal(state_id):
            return path
        if max_depth is not None and len(path) >= max_depth:
            continue
        for action, target in model.outgoing(state_id):
            if target not in visited:
                visited.add(target)
                step = PlannedStep(action, target)
                queue.append((target, [*path, step]))
    return None
