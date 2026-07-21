from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from arc_schema.core import Action, Observation, materialize_snapshot, rle_to_frame


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class WorldModelState:
    id: str
    snapshot: JsonDict
    goal: bool = False


@dataclass(frozen=True)
class WorldModelTransition:
    from_id: str
    action: Action
    to_id: str


class WorldModelValidationError(ValueError):
    """Raised when a model payload cannot be safely materialized."""


# Backward-compatible alias used by older call sites.
WorldModelError = WorldModelValidationError


class DeclarativeWorldModel:
    """Finite-state machine over known or materialized observation snapshots."""

    def __init__(
        self,
        states: dict[str, WorldModelState],
        transitions: list[WorldModelTransition],
        *,
        max_states: int = 24,
        max_transitions: int = 64,
    ) -> None:
        if len(states) > max_states:
            raise WorldModelValidationError(f"too many states: {len(states)} > {max_states}")
        if len(transitions) > max_transitions:
            raise WorldModelValidationError(
                f"too many transitions: {len(transitions)} > {max_transitions}"
            )
        self.states = states
        self._edges: dict[tuple[str, str], tuple[Action, str]] = {}
        for edge in transitions:
            if edge.from_id not in states or edge.to_id not in states:
                raise WorldModelValidationError("transition references unknown state")
            key = (edge.from_id, edge.action.key())
            if key in self._edges:
                raise WorldModelValidationError("duplicate transition for state/action")
            self._edges[key] = (edge.action, edge.to_id)

    @classmethod
    def from_dict(
        cls,
        payload: JsonDict,
        known_snapshots: dict[str, JsonDict] | None = None,
        *,
        catalog: dict[str, JsonDict] | None = None,
        known_levels: int = 0,
        max_states: int = 24,
        max_transitions: int = 64,
        allow_raw_snapshots: bool = False,
    ) -> DeclarativeWorldModel:
        snapshots = catalog if catalog is not None else (known_snapshots or {})
        return parse_world_model(
            payload,
            snapshots,
            known_levels=known_levels,
            max_states=max_states,
            max_transitions=max_transitions,
            allow_raw_snapshots=allow_raw_snapshots,
        )

    def state_for_observation(self, observation: Observation) -> WorldModelState | None:
        snapshot = observation.snapshot()
        matches = [state for state in self.states.values() if state.snapshot == snapshot]
        if len(matches) != 1:
            return None
        return matches[0]

    def is_goal(self, state_id: str) -> bool:
        return self.states[state_id].goal

    def outgoing(self, state_id: str) -> Iterable[tuple[Action, str]]:
        for (source, _action_key), (action, target) in self._edges.items():
            if source == state_id:
                yield action, target

    def predict(
        self,
        observation_or_state: Observation | WorldModelState,
        action: Action,
    ) -> WorldModelState | None:
        if isinstance(observation_or_state, Observation):
            source = self.state_for_observation(observation_or_state)
        else:
            source = observation_or_state
        if source is None:
            return None
        edge = self._edges.get((source.id, action.key()))
        if edge is None:
            return None
        return self.states[edge[1]]

    def goal_state_ids(self) -> set[str]:
        return {state.id for state in self.states.values() if state.goal}


def snapshot_to_observation(snapshot: JsonDict) -> Observation:
    return Observation(
        game_id=str(snapshot["game_id"]),
        state=str(snapshot["state"]),
        levels_completed=int(snapshot["levels_completed"]),
        win_levels=int(snapshot["win_levels"]),
        available_actions=tuple(int(item) for item in snapshot["available_actions"]),
        frame=rle_to_frame(list(snapshot["frame_rle"])),
        frame_count=0,
    )


def _resolve_state_snapshot(
    state: JsonDict,
    catalog: dict[str, JsonDict],
    *,
    known_levels: int,
    allow_raw_snapshots: bool,
) -> JsonDict:
    if "snapshot_ref" in state:
        ref = str(state["snapshot_ref"])
        if ref not in catalog:
            raise WorldModelValidationError(f"unknown snapshot_ref {ref}")
        if any(key in state for key in ("snapshot", "snapshot_patch", "base_ref")):
            raise WorldModelValidationError("snapshot_ref cannot combine with other snapshot fields")
        return catalog[ref]

    if "snapshot_patch" in state or "base_ref" in state:
        base_ref = state.get("base_ref")
        if not isinstance(base_ref, str) or base_ref not in catalog:
            raise WorldModelValidationError("snapshot_patch requires a known base_ref")
        patch = state.get("snapshot_patch")
        if not isinstance(patch, dict):
            raise WorldModelValidationError("snapshot_patch must be an object")
        metadata = dict(patch.get("metadata", {}))
        if "levels_completed" in metadata:
            claimed = int(metadata["levels_completed"])
            # Allow a single hypothesized level advance only on explicitly marked goals.
            max_allowed = known_levels + (1 if bool(state.get("goal")) else 0)
            if claimed > max_allowed:
                raise WorldModelValidationError(
                    "cannot invent levels_completed beyond observed evidence"
                )
        try:
            return materialize_snapshot(catalog[base_ref], patch=patch)
        except ValueError as exc:
            raise WorldModelValidationError(str(exc)) from exc

    if "snapshot" in state:
        if not allow_raw_snapshots:
            raise WorldModelValidationError(
                "raw snapshot copies are forbidden; use snapshot_ref or snapshot_patch"
            )
        snapshot = state["snapshot"]
        if not isinstance(snapshot, dict):
            raise WorldModelValidationError("snapshot must be an object")
        return dict(snapshot)

    raise WorldModelValidationError("state requires snapshot_ref or snapshot_patch")


def parse_world_model(
    payload: JsonDict,
    catalog: dict[str, JsonDict],
    *,
    known_levels: int = 0,
    max_states: int = 24,
    max_transitions: int = 64,
    allow_raw_snapshots: bool = False,
) -> DeclarativeWorldModel:
    raw_states = payload.get("states")
    raw_transitions = payload.get("transitions")
    if not isinstance(raw_states, list) or not isinstance(raw_transitions, list):
        raise WorldModelValidationError("world model requires states and transitions lists")

    states: dict[str, WorldModelState] = {}
    for item in raw_states:
        if not isinstance(item, dict):
            raise WorldModelValidationError("each state must be an object")
        state_id = str(item.get("id", ""))
        if not state_id or state_id in states:
            raise WorldModelValidationError("state ids must be unique and non-empty")
        snapshot = _resolve_state_snapshot(
            item,
            catalog,
            known_levels=known_levels,
            allow_raw_snapshots=allow_raw_snapshots,
        )
        states[state_id] = WorldModelState(
            id=state_id,
            snapshot=snapshot,
            goal=bool(item.get("goal", False)),
        )

    transitions: list[WorldModelTransition] = []
    for item in raw_transitions:
        if not isinstance(item, dict):
            raise WorldModelValidationError("each transition must be an object")
        action_payload = item.get("action")
        if not isinstance(action_payload, dict) or "id" not in action_payload:
            raise WorldModelValidationError("transition action requires id")
        transitions.append(
            WorldModelTransition(
                from_id=str(item.get("from", "")),
                action=Action(
                    id=int(action_payload["id"]),
                    data=dict(action_payload.get("data", {})),
                ),
                to_id=str(item.get("to", "")),
            )
        )
    return DeclarativeWorldModel(
        states,
        transitions,
        max_states=max_states,
        max_transitions=max_transitions,
    )


def build_observation_catalog(
    observations: list[Observation],
    *,
    prefix: str = "obs",
) -> dict[str, JsonDict]:
    catalog: dict[str, JsonDict] = {}
    for index, observation in enumerate(observations):
        catalog[f"{prefix}-{index}"] = observation.snapshot()
    return catalog
