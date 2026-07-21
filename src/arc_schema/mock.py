from __future__ import annotations

import json
from typing import Any

from arc_schema.core import Action, Observation, Usage, encode_row
from arc_schema.deepseek_client import ModelResponse


def toy_observation(position: int) -> Observation:
    return Observation(
        game_id="toy",
        state="WIN" if position == 2 else "NOT_FINISHED",
        levels_completed=1 if position == 2 else 0,
        win_levels=1,
        available_actions=(1, 2),
        frame=((position, 0, 0),),
        frame_count=1,
    )


class ToyEnvironment:
    def __init__(self) -> None:
        self.position = 0
        self._current = toy_observation(0)
        self.actions = 0

    @property
    def current(self) -> Observation:
        return self._current

    def step(self, action: Action) -> Observation:
        if action.id not in self._current.available_actions:
            raise ValueError("illegal toy action")
        if action.id == 1:
            self.position = min(2, self.position + 1)
        self.actions += 1
        self._current = toy_observation(self.position)
        return self._current

    def score_summary(self) -> dict[str, Any]:
        won = self.position == 2
        return {
            "score": 100.0 if won else 0.0,
            "levels_completed": int(won),
            "completed": won,
        }


def _payload_from_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            try:
                value = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "current" in value:
                return value
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = str(part.get("text", ""))
                    marker = "{"
                    if marker in text:
                        try:
                            value = json.loads(text[text.index(marker) :])
                        except json.JSONDecodeError:
                            continue
                        if isinstance(value, dict) and "current" in value:
                            return value
    return {}


def _ref_for_position(payload: dict[str, Any], position: int) -> str | None:
    target = toy_observation(position).fingerprint
    current = payload.get("current", {})
    if current.get("fingerprint") == target:
        return str(current["snapshot_ref"])
    for item in payload.get("history_deltas", []):
        if item.get("before_fingerprint") == target:
            return str(item["before_ref"])
        if item.get("after_fingerprint") == target:
            return str(item["after_ref"])
    return None


def _state_spec(state_id: str, position: int, base_ref: str, *, goal: bool) -> dict[str, Any]:
    obs = toy_observation(position)
    return {
        "id": state_id,
        "base_ref": base_ref,
        "snapshot_patch": {
            "rows": [{"y": 0, "rle": encode_row(obs.frame[0])}],
            "metadata": {
                "state": obs.state,
                "levels_completed": obs.levels_completed,
                "available_actions": list(obs.available_actions),
            },
        },
        "goal": goal,
    }


class DeterministicMockClient:
    """No-network client used by tests and the mock A/B command."""

    def complete_json(self, messages: list[dict[str, Any]], purpose: str) -> ModelResponse:
        if purpose == "baseline_action":
            value: dict[str, Any] = {"action": {"id": 1, "data": {}}}
        elif purpose == "world_model":
            payload = _payload_from_messages(messages)
            current = payload.get("current", {})
            current_ref = str(current.get("snapshot_ref", "obs_missing"))
            states: list[dict[str, Any]] = []
            transitions: list[dict[str, Any]] = []
            seen_refs: dict[int, str] = {}

            def ensure_position(position: int) -> str:
                if position in seen_refs:
                    return f"p{position}"
                ref = _ref_for_position(payload, position)
                state_id = f"p{position}"
                if ref is not None:
                    states.append(
                        {
                            "id": state_id,
                            "snapshot_ref": ref,
                            "goal": position == 2,
                        }
                    )
                    seen_refs[position] = ref
                else:
                    states.append(
                        _state_spec(state_id, position, current_ref, goal=position == 2)
                    )
                    seen_refs[position] = current_ref
                return state_id

            # Cover positions needed for backtest + one-step progress.
            for item in payload.get("history_deltas", []):
                before_fp = str(item.get("before_fingerprint", ""))
                after_fp = str(item.get("after_fingerprint", ""))
                for position in range(3):
                    if toy_observation(position).fingerprint in {before_fp, after_fp}:
                        ensure_position(position)
            current_fp = str(current.get("fingerprint", ""))
            for position in range(3):
                if toy_observation(position).fingerprint == current_fp:
                    ensure_position(position)
            # Always include a path toward the goal from the live position.
            live = 0
            for position in range(3):
                if toy_observation(position).fingerprint == current_fp:
                    live = position
                    break
            for position in range(live, 3):
                ensure_position(position)

            edge_keys: set[tuple[str, str]] = set()

            def add_edge(source: str, action: dict[str, Any], target: str) -> None:
                key = (source, json.dumps(action, sort_keys=True))
                if key in edge_keys:
                    return
                edge_keys.add(key)
                transitions.append({"from": source, "action": action, "to": target})

            for position in list(seen_refs):
                source = f"p{position}"
                add_edge(source, {"id": 1, "data": {}}, f"p{min(position + 1, 2)}")
                add_edge(source, {"id": 2, "data": {}}, source)
                ensure_position(min(position + 1, 2))

            value = {"states": states, "transitions": transitions}
        else:
            raise ValueError(f"unsupported mock purpose {purpose}")
        text = json.dumps(value)
        return ModelResponse(
            value=value,
            raw_text=text,
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_seconds=0.0,
            attempts=1,
        )
