from __future__ import annotations

"""
无网络 Toy 环境与确定性模拟模型：验证 Schema 闭环而不调用真实 ARC / API。

阅读导引：
- ToyEnvironment：三格前进游戏（位置 0→1→2 即 WIN），最小真实环境替身
- DeterministicMockClient：脚本化工具链（write_code → explore → backtest → BFS → planned）
- CompoundDeterministicMockClient：workspace-native，两次 schema_cycle 跑通认证+BFS+提交
- TOY_STEP_SOURCE：可过 Toy 的最小世界模型源码
"""

import json
from typing import Any

from arc_schema.core import Action, Observation, Usage, encode_row
from arc_schema.deepseek_client import ModelResponse


def toy_observation(position: int, *, state: str | None = None) -> Observation:
    """按位置构造 Toy 观察；position==2 时为 WIN。"""
    if state is None:
        state = "WIN" if position == 2 else "NOT_FINISHED"
    levels = 1 if state == "WIN" or (state == "NOT_FINISHED" and position == 2) else 0
    if state == "WIN":
        levels = 1
    actions = (0,) if state == "GAME_OVER" else (1, 2)
    return Observation(
        game_id="toy",
        state=state,
        levels_completed=levels,
        win_levels=1,
        available_actions=actions,
        frame=((position, 0, 0),),
        frame_count=1,
    )


class ToyEnvironment:
    """最小可交互环境：ACTION1 前进，到位置 2 过关；可选 lethal_action 触发 GAME_OVER。"""

    def __init__(self, *, lethal_action: int | None = None) -> None:
        self.position = 0
        self._current = toy_observation(0)
        self.actions = 0
        self.lethal_action = lethal_action
        self.resets = 0

    @property
    def current(self) -> Observation:
        return self._current

    def step(self, action: Action) -> Observation:
        if self._current.state == "GAME_OVER":
            if action.id != 0:
                raise ValueError("only RESET(0) allowed after GAME_OVER")
            self.resets += 1
            self.position = 0
            self.actions += 1
            self._current = toy_observation(0)
            return self._current
        if action.id not in self._current.available_actions and not (
            action.id == 0 and self._current.state in {"GAME_OVER", "WIN"}
        ):
            raise ValueError("illegal toy action")
        if self.lethal_action is not None and action.id == self.lethal_action:
            self.actions += 1
            self._current = toy_observation(self.position, state="GAME_OVER")
            return self._current
        if action.id == 1:
            self.position = min(2, self.position + 1)
        self.actions += 1
        self._current = toy_observation(self.position)
        return self._current

    def score_summary(self) -> dict[str, Any]:
        won = self.position == 2 and self._current.state == "WIN"
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


def _last_json_object(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
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


# 可过 Toy 的最小 legacy 世界模型：ACTION1 前进并在终点标 WIN。
TOY_STEP_SOURCE = """\
def step(state, action):
    nxt = state.copy()
    if int(action["id"]) == 1:
        pos = int(nxt.frame[0][0])
        pos = min(2, pos + 1)
        nxt.frame[0][0] = pos
        if pos == 2:
            nxt.state = "WIN"
            nxt.levels_completed = 1
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed >= 1
"""


class DeterministicMockClient:
    """无网络脚本客户端：按固定阶段返回审议工具调用，供测试与 mock A/B。"""

    def __init__(self) -> None:
        self.calls = 0
        self._deliberation_phase = 0

    def complete_json(self, messages: list[dict[str, Any]], purpose: str) -> ModelResponse:
        if purpose == "baseline_action":
            value: dict[str, Any] = {"action": {"id": 1, "data": {}}}
        elif purpose == "deliberation":
            value = self._deliberation_response(messages)
        elif purpose == "world_model":
            value = self._fsm_world_model(messages)
        else:
            raise ValueError(f"unsupported mock purpose {purpose}")
        self.calls += 1
        text = json.dumps(value)
        return ModelResponse(
            value=value,
            raw_text=text,
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_seconds=0.0,
            attempts=1,
        )

    def _deliberation_response(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        # Scripted Schema loop:
        # write_code → explore commit (gather Timeline) → backtest → bfs → planned commit.
        phase = self._deliberation_phase
        self._deliberation_phase += 1
        if phase == 0:
            return {"tool": "write_code", "args": {"source": TOY_STEP_SOURCE}}
        if phase == 1:
            return {
                "tool": "write_notes",
                "args": {
                    "text": (
                        "# Working notes\n"
                        "## Hypotheses\n"
                        "- H1: ACTION1 advances position toward WIN.\n"
                    )
                },
            }
        if phase == 2:
            return {
                "tool": "commit_actions",
                "args": {
                    "kind": "exploration",
                    "actions": [{"id": 1, "data": {}}],
                    "reason": "gather one transition before certify",
                },
            }
        if phase == 3:
            return {"tool": "run_backtest", "args": {}}
        if phase == 4:
            return {"tool": "run_bfs", "args": {}}
        if phase == 5:
            plan_id = str(_last_json_object(messages).get("plan_id", ""))
            return {
                "tool": "commit_actions",
                "args": {
                    "kind": "planned",
                    "plan_id": plan_id,
                    "actions": [{"id": 1, "data": {}}],
                    "reason": "toy plan to WIN from position 1",
                },
            }
        return {"tool": "done", "args": {"reason": "already committed"}}

    def _fsm_world_model(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
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
                states.append(_state_spec(state_id, position, current_ref, goal=position == 2))
                seen_refs[position] = current_ref
            return state_id

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

        return {"states": states, "transitions": transitions}


class CompoundDeterministicMockClient:
    """Workspace-native 模拟：两次 schema_cycle 完成探索 → 改码认证 → BFS planned。"""

    workspace_native = True

    def __init__(self) -> None:
        self.calls = 0
        self.workspace = None

    def bind_workspace(self, workspace) -> None:
        self.workspace = workspace

    def complete_json(self, messages, purpose):
        del messages
        assert purpose == "deliberation"
        if self.calls == 0:
            value = {
                "tool": "schema_cycle",
                "args": {
                    "strategy": "exploration",
                    "hypothesis_updates": {
                        "hypotheses": [
                            {
                                "id": "H_action1_progress",
                                "statement": "ACTION1 advances a progress state.",
                                "status": "active",
                            }
                        ],
                        "evidence_seq": [],
                        "reason": "register the initial action hypothesis",
                    },
                    "exploration_action": {"id": 1, "data": {}},
                    "decision_record": {
                        "hypotheses": ["H_action1_progress"],
                        "evidence_seq": [],
                        "expected_observation": "position advances",
                        "revision_trigger": "position does not advance",
                    },
                    "rationale": "gather one transition before certification",
                },
            }
        else:
            value = {
                "tool": "schema_cycle",
                "args": {
                    "strategy": "auto",
                    "workspace_edits": {
                        "source": TOY_STEP_SOURCE,
                        "notes_text": (
                            "# Toy mechanism\nACTION1 advances position; exact replay then BFS.\n"
                        ),
                    },
                    "hypothesis_updates": {
                        "hypotheses": [
                            {
                                "id": "H_action1_progress",
                                "statement": "ACTION1 increments position toward WIN.",
                                "status": "supported",
                            }
                        ],
                        "evidence_seq": [1],
                        "reason": "the first transition supports progress",
                    },
                    "exploration_action": {"id": 2, "data": {}},
                    "decision_record": {
                        "hypotheses": ["H_action1_progress"],
                        "evidence_seq": [1],
                        "expected_observation": "BFS reaches WIN",
                        "revision_trigger": "any prequential mismatch",
                    },
                    "rationale": "certify the edited model and execute exact BFS",
                },
            }
        self.calls += 1
        text = json.dumps(value)
        return ModelResponse(
            value=value,
            raw_text=text,
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_seconds=0.0,
            attempts=1,
        )
