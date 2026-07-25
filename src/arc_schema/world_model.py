from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from arc_schema.core import (
    Action,
    Observation,
    Transition,
    materialize_snapshot,
    rle_to_frame,
)


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


def build_history_skeleton(
    current: Observation,
    history: list[Transition],
    *,
    limit: int,
) -> JsonDict:
    """Deterministic FSM covering the compact-context history window + current."""
    window = history[-limit:]
    states: list[JsonDict] = []
    transitions: list[JsonDict] = []
    fingerprint_to_id: dict[str, str] = {}

    def ensure(observation: Observation) -> str:
        fingerprint = observation.fingerprint
        existing = fingerprint_to_id.get(fingerprint)
        if existing is not None:
            return existing
        state_id = f"h{len(fingerprint_to_id)}"
        fingerprint_to_id[fingerprint] = state_id
        states.append(
            {
                "id": state_id,
                "snapshot_ref": f"obs_{fingerprint}",
                "goal": False,
            }
        )
        return state_id

    for item in window:
        ensure(item.before)
        ensure(item.after)
    ensure(current)

    seen_edges: set[tuple[str, str]] = set()
    for item in window:
        from_id = fingerprint_to_id[item.before.fingerprint]
        to_id = fingerprint_to_id[item.after.fingerprint]
        action_payload = {"id": item.action.id, "data": dict(item.action.data)}
        edge_key = (from_id, item.action.key())
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        transitions.append({"from": from_id, "action": action_payload, "to": to_id})

    return {
        "states": states,
        "transitions": transitions,
        "current_state_id": fingerprint_to_id[current.fingerprint],
    }


def merge_world_model_extension(skeleton: JsonDict, extension: JsonDict) -> JsonDict:
    """
    Merge model-proposed extensions onto a history skeleton.

    Skeleton transitions win on (from, action) conflicts. Extension may:
    - mark known snapshot_ref states as goals;
    - add hypothesized states via base_ref + snapshot_patch;
    - add new outgoing transitions;
    - optionally list goal_state_ids.
    """
    if not isinstance(extension, dict):
        raise WorldModelValidationError("world model extension must be an object")

    skeleton_states = skeleton.get("states")
    skeleton_transitions = skeleton.get("transitions")
    if not isinstance(skeleton_states, list) or not isinstance(skeleton_transitions, list):
        raise WorldModelValidationError("skeleton requires states and transitions lists")

    merged_states: dict[str, JsonDict] = {}
    ref_to_id: dict[str, str] = {}
    for item in skeleton_states:
        if not isinstance(item, dict):
            raise WorldModelValidationError("skeleton state must be an object")
        state_id = str(item["id"])
        merged_states[state_id] = {
            "id": state_id,
            "snapshot_ref": str(item["snapshot_ref"]),
            "goal": bool(item.get("goal", False)),
        }
        ref_to_id[str(item["snapshot_ref"])] = state_id

    id_alias: dict[str, str] = {state_id: state_id for state_id in merged_states}

    raw_states = extension.get("states", [])
    if raw_states is None:
        raw_states = []
    if not isinstance(raw_states, list):
        raise WorldModelValidationError("extension states must be a list")

    for item in raw_states:
        if not isinstance(item, dict):
            raise WorldModelValidationError("each extension state must be an object")
        ext_id = str(item.get("id", ""))
        if not ext_id:
            raise WorldModelValidationError("extension state ids must be non-empty")

        if "snapshot_ref" in item:
            ref = str(item["snapshot_ref"])
            if ref in ref_to_id:
                canonical = ref_to_id[ref]
                id_alias[ext_id] = canonical
                if bool(item.get("goal", False)):
                    merged_states[canonical]["goal"] = True
                continue
            if ext_id in merged_states:
                raise WorldModelValidationError(f"extension reuses seeded state id {ext_id}")
            merged_states[ext_id] = {
                "id": ext_id,
                "snapshot_ref": ref,
                "goal": bool(item.get("goal", False)),
            }
            ref_to_id[ref] = ext_id
            id_alias[ext_id] = ext_id
            continue

        if "snapshot_patch" in item or "base_ref" in item:
            state_id = ext_id
            suffix = 0
            while state_id in merged_states:
                suffix += 1
                state_id = f"{ext_id}_{suffix}"
            payload = {
                "id": state_id,
                "base_ref": item.get("base_ref"),
                "snapshot_patch": item.get("snapshot_patch"),
                "goal": bool(item.get("goal", False)),
            }
            merged_states[state_id] = payload
            id_alias[ext_id] = state_id
            continue

        if "snapshot" in item:
            raise WorldModelValidationError(
                "raw snapshot copies are forbidden; use snapshot_ref or snapshot_patch"
            )
        raise WorldModelValidationError("extension state requires snapshot_ref or snapshot_patch")

    goal_ids = extension.get("goal_state_ids", [])
    if goal_ids is None:
        goal_ids = []
    if not isinstance(goal_ids, list):
        raise WorldModelValidationError("goal_state_ids must be a list")
    for raw_id in goal_ids:
        target = id_alias.get(str(raw_id), str(raw_id))
        if target not in merged_states:
            raise WorldModelValidationError(f"goal_state_ids references unknown state {raw_id}")
        merged_states[target]["goal"] = True

    merged_transitions: list[JsonDict] = []
    edge_keys: set[tuple[str, str]] = set()

    def add_transition(from_id: str, action_payload: JsonDict, to_id: str) -> None:
        action = Action(
            id=int(action_payload["id"]),
            data=dict(action_payload.get("data", {})),
        )
        key = (from_id, action.key())
        if key in edge_keys:
            return
        edge_keys.add(key)
        merged_transitions.append(
            {
                "from": from_id,
                "action": {"id": action.id, "data": dict(action.data)},
                "to": to_id,
            }
        )

    for item in skeleton_transitions:
        if not isinstance(item, dict):
            raise WorldModelValidationError("skeleton transition must be an object")
        action_payload = item.get("action")
        if not isinstance(action_payload, dict):
            raise WorldModelValidationError("skeleton transition action must be an object")
        add_transition(str(item["from"]), action_payload, str(item["to"]))

    raw_transitions = extension.get("transitions", [])
    if raw_transitions is None:
        raw_transitions = []
    if not isinstance(raw_transitions, list):
        raise WorldModelValidationError("extension transitions must be a list")

    for item in raw_transitions:
        if not isinstance(item, dict):
            raise WorldModelValidationError("each extension transition must be an object")
        action_payload = item.get("action")
        if not isinstance(action_payload, dict) or "id" not in action_payload:
            raise WorldModelValidationError("transition action requires id")
        from_raw = str(item.get("from", ""))
        to_raw = str(item.get("to", ""))
        from_id = id_alias.get(from_raw, from_raw)
        to_id = id_alias.get(to_raw, to_raw)
        if from_id not in merged_states or to_id not in merged_states:
            raise WorldModelValidationError("transition references unknown state")
        add_transition(from_id, action_payload, to_id)

    return {"states": list(merged_states.values()), "transitions": merged_transitions}