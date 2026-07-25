from __future__ import annotations

"""
有界 Schema 内环：理论化 → 认证 → 规划 → 提交动作。

本模块不直接操作真实环境；LLM 每轮只能返回一个 JSON 工具调用，由 DeliberationSession
在 Workspace / ProgramWorldModel 上执行，最终通过 commit_actions 把动作交给 runner。

主流程（DeliberationSession.run）：
1. 组装 system 提示 + 当前观察/历史/代码/认证状态等上下文；
2. 在 max_turns / 模型调用次数 / 花费预算内循环调用 LLM；
3. 分发工具：改代码、回测、BFS、笔记、提议探索；非法调用则反馈错误继续；
4. commit_actions 校验通过后返回 CommitRequest；done / 预算耗尽 / 达上限则无 commit。

认证约定：run_backtest 全 Timeline 通过后 workspace.certified=True；planned 提交与
run_bfs 都要求已认证；exploration 可在未认证时提交恰好一个探索动作。
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from arc_schema.context import next_explore_action, untried_actions
from arc_schema.core import Action, Observation, RunMetrics, Transition, canonical_json
from arc_schema.deepseek_client import ModelClient
from arc_schema.history import AppendOnlyJournal
from arc_schema.program_world_model import (
    ProgramWorldModel,
    backtest_program,
    bfs_program_plan,
)
from arc_schema.sandbox import SandboxError
from arc_schema.workspace import Workspace


JsonDict = dict[str, Any]


# 发给 LLM 的系统提示（保持英文，作为模型指令；勿改成中文以免改变行为）
SCHEMA_SYSTEM = """You are a Schema-style physicist for an ARC-AGI-3 game.
You must jointly invent state grounding (objects/variables) and mechanisms.
Encode your theory ONLY as Python in world_model.py defining:
  step(state, action) -> GridState
  is_goal(state) -> bool
Helpers available inside the sandbox: GridState, find_color, bbox, neighbors4, deepcopy.
NO imports, NO file/network access, NO dunder attributes.

Action meanings must be inferred from recorded transitions only — never assume
ACTION1-4 semantics from external game source code.

The Timeline is the full interaction Record across lives and level progress.
After a GAME_OVER, the harness may RESET while keeping your world_model.py, notes,
and prior transitions. Low-level experience remains valid evidence: any new hypothesis
must still pass run_backtest on the FULL Timeline (RESET steps are skipped).
Do NOT assume earlier rules stay unchanged after a level-up or death — revise
representation and/or mechanisms when backtest fails or last_mismatch is set.

Prefer apply_patch for small edits to world_model.py; use write_code only for
full rewrites. After any code change, run_backtest on the FULL Timeline before
planning. If last_mismatch is present, revise representation or rules to explain it.
When multiple rules fit history, commit one discriminating exploration action.

CRITICAL efficiency rules:
- With little Timeline evidence, prefer commit_actions kind=exploration SOON
  (often within the first 2-4 tool turns) instead of endless rewrite loops.
- At most a couple of write_code/apply_patch attempts per deliberation before
  either run_backtest+commit or a single explore commit.
- Do not spend the whole turn budget only rewriting code.
- Prefer propose_experiment then commit_actions over another full rewrite.

Tools (deliberation does not touch the real environment):
- write_code / apply_patch: edit world_model.py
- run_backtest: replay step() on the FULL Timeline (must pass before planning)
- run_bfs: search inside a certified model for is_goal
- write_notes / read_notes: persistent working memory
- propose_experiment: suggest one informative explore action
- commit_actions: the ONLY channel that executes real environment actions

Return one JSON object per turn with EXACT schemas:
{"tool":"write_code","args":{"source":"<full world_model.py text>"}}
{"tool":"apply_patch","args":{"old":"<unique old snippet>","new":"<replacement>"}}
{"tool":"run_backtest","args":{}}
{"tool":"run_bfs","args":{}}
{"tool":"write_notes","args":{"text":"..."}}
{"tool":"read_notes","args":{}}
{"tool":"propose_experiment","args":{}}
{"tool":"commit_actions","args":{"kind":"planned"|"exploration","actions":[{"id":1,"data":{}}]}}
{"tool":"done","args":{"reason":"..."}}

In step(), action is a dict: use int(action["id"]), not action == 1.
Do not commit action id 0 (RESET); the outer harness handles life resets.
"""


TOOL_NAMES = {
    "write_code",
    "apply_patch",
    "run_backtest",
    "run_bfs",
    "write_notes",
    "read_notes",
    "propose_experiment",
    "commit_actions",
    "done",
}


@dataclass
class CommitRequest:
    """内环结束时交给 runner 在真实环境执行的动作包。"""

    actions: list[Action]
    kind: str  # "planned" | "exploration"
    reason: str = ""


@dataclass
class DeliberationResult:
    """一次内环运行的结果：可选 commit、工具轨迹与结束原因。"""

    commit: CommitRequest | None
    tool_trace: list[JsonDict] = field(default_factory=list)
    reason: str = ""


def _parse_tool_call(value: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """从模型 JSON 中解析 tool 名与 args；未知工具则报错。"""
    tool = str(value.get("tool", "")).strip()
    args = value.get("args", {})
    if not isinstance(args, dict):
        args = {}
    if tool not in TOOL_NAMES:
        raise ValueError(f"unknown tool {tool}")
    return tool, args


class DeliberationSession:
    """有界 Schema 内环：理论化 → 认证 → 规划 → 提交。"""

    def __init__(
        self,
        client: ModelClient,
        workspace: Workspace,
        *,
        max_turns: int,
        planner_max_nodes: int,
        max_plan_steps: int,
        max_model_calls: int,
        max_spend_usd: float = 0.0,
    ) -> None:
        self.client = client
        self.workspace = workspace
        self.max_turns = max_turns
        self.planner_max_nodes = planner_max_nodes
        self.max_plan_steps = max_plan_steps
        self.max_model_calls = max_model_calls
        self.max_spend_usd = max_spend_usd

    def run(
        self,
        current: Observation,
        history: list[Transition],
        journal: AppendOnlyJournal,
        metrics: RunMetrics,
    ) -> DeliberationResult:
        """运行多轮工具循环，直到 commit / done / 预算或轮次耗尽。"""
        tool_trace: list[JsonDict] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SCHEMA_SYSTEM},
            {
                "role": "user",
                "content": canonical_json(self._context_payload(current, history)),
            },
        ]
        for _turn in range(self.max_turns):
            if metrics.model_calls >= self.max_model_calls:
                return DeliberationResult(None, tool_trace, "model_call_budget")
            if self.max_spend_usd > 0 and (metrics.usage.estimated_cost_usd or 0.0) >= self.max_spend_usd:
                return DeliberationResult(None, tool_trace, "spend_budget")
            metrics.model_calls += 1
            journal.append("model_request", {"purpose": "deliberation", "messages": messages[-2:]})
            try:
                response = self.client.complete_json(messages, "deliberation")
            except Exception as exc:
                metrics.model_failures += 1
                metrics.model_api_attempts += int(getattr(exc, "attempts", 0))
                error_usage = getattr(exc, "usage", None)
                if error_usage is not None:
                    metrics.usage.add(error_usage)
                journal.append(
                    "model_error",
                    {
                        "purpose": "deliberation",
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "api_attempts": int(getattr(exc, "attempts", 0)),
                    },
                )
                return DeliberationResult(None, tool_trace, f"model_error:{exc}")
            metrics.model_api_attempts += response.attempts
            metrics.usage.add(response.usage)
            journal.append(
                "model_response",
                {
                    "purpose": "deliberation",
                    "raw_text": response.raw_text,
                    "parsed": response.value,
                    "usage": asdict(response.usage),
                    "latency_seconds": response.latency_seconds,
                    "api_attempts": response.attempts,
                },
            )
            if self.max_spend_usd > 0 and (metrics.usage.estimated_cost_usd or 0.0) >= self.max_spend_usd:
                return DeliberationResult(None, tool_trace, "spend_budget")
            try:
                tool, args = _parse_tool_call(response.value)
            except Exception as exc:
                observation = {"ok": False, "error": f"bad tool call: {exc}"}
                tool_trace.append({"tool": "invalid", "args": response.value, "result": observation})
                messages.append({"role": "assistant", "content": response.raw_text})
                messages.append({"role": "user", "content": canonical_json(observation)})
                continue

            if tool == "done":
                tool_trace.append({"tool": tool, "args": args, "result": {"ok": True}})
                return DeliberationResult(None, tool_trace, str(args.get("reason", "done")))

            if tool == "commit_actions":
                commit, observation = self._handle_commit(args, current, history)
                tool_trace.append({"tool": tool, "args": args, "result": observation})
                journal.append("deliberation_tool", tool_trace[-1])
                if commit is not None:
                    return DeliberationResult(commit, tool_trace, "commit")
                messages.append({"role": "assistant", "content": response.raw_text})
                messages.append({"role": "user", "content": canonical_json(observation)})
                continue

            observation = self._dispatch_tool(tool, args, current, history, metrics, journal)
            tool_trace.append({"tool": tool, "args": args, "result": observation})
            journal.append("deliberation_tool", tool_trace[-1])
            messages.append({"role": "assistant", "content": response.raw_text})
            messages.append({"role": "user", "content": canonical_json(observation)})

        return DeliberationResult(None, tool_trace, "max_turns")

    def _context_payload(self, current: Observation, history: list[Transition]) -> JsonDict:
        """构造每轮发给模型的用户上下文（观察、近期转移、代码、认证状态等）。"""
        recent = []
        for item in history[-8:]:
            recent.append(
                {
                    "action": {"id": item.action.id, "data": item.action.data},
                    "before_fp": item.before.fingerprint[:16],
                    "after_fp": item.after.fingerprint[:16],
                    "delta": item.delta().to_dict(),
                    "levels": {
                        "before": item.before.levels_completed,
                        "after": item.after.levels_completed,
                    },
                }
            )
        return {
            "current": {
                "snapshot": current.snapshot(),
                "fingerprint": current.fingerprint,
                "available_actions": list(current.available_actions),
                "untried_action_ids": untried_actions(current, history),
            },
            "timeline_len": len(history),
            "recent_transitions": recent,
            "world_model_py": self.workspace.read_code(),
            "notes_md": self.workspace.read_notes()[:4000],
            "certified": self.workspace.certified,
            "last_backtest": (
                asdict(self.workspace.last_backtest)
                if self.workspace.last_backtest is not None
                else None
            ),
            "last_mismatch": self.workspace.last_mismatch,
            "instruction": (
                "If timeline_len is small, commit one exploration action quickly. "
                "Prefer apply_patch + run_backtest, then either run_bfs+commit_actions "
                "(only if certified) or commit a single explore action. After level-up "
                "or life_reset, re-certify before trusting old plans. Do not loop on "
                "write_code without committing an environment action."
            ),
        }

    def _dispatch_tool(
        self,
        tool: str,
        args: dict[str, Any],
        current: Observation,
        history: list[Transition],
        metrics: RunMetrics,
        journal: AppendOnlyJournal,
    ) -> JsonDict:
        """执行除 commit_actions / done 以外的工具，返回观察结果给下一轮模型。"""
        del journal
        try:
            if tool == "write_code":
                source = str(
                    args.get("source")
                    or args.get("code")
                    or args.get("content")
                    or args.get("world_model_py")
                    or ""
                )
                if not source.strip():
                    return {
                        "ok": False,
                        "error": "source required (use args.source with full world_model.py text)",
                    }
                self.workspace.write_code(source)
                return {
                    "ok": True,
                    "version": self.workspace.version,
                    "certified": False,
                    "message": "code written; run_backtest required before planning",
                }
            if tool == "apply_patch":
                old = str(args.get("old", ""))
                new = str(args.get("new", ""))
                if not old:
                    return {"ok": False, "error": "apply_patch requires unique args.old"}
                self.workspace.apply_patch(old, new)
                return {
                    "ok": True,
                    "version": self.workspace.version,
                    "certified": False,
                    "message": "patch applied; run_backtest required before planning",
                }
            if tool == "write_notes":
                self.workspace.write_notes(str(args.get("text", "")))
                return {"ok": True}
            if tool == "read_notes":
                return {"ok": True, "text": self.workspace.read_notes()}
            if tool == "run_backtest":
                model = self.workspace.model()
                result = backtest_program(model, history)
                self.workspace.last_backtest = result
                self.workspace.certified = bool(result.passed)
                if not result.passed:
                    metrics.backtest_failures += 1
                return {"ok": True, "result": asdict(result), "certified": self.workspace.certified}
            if tool == "run_bfs":
                if not self.workspace.certified:
                    return {"ok": False, "error": "run_bfs requires a certified world model"}
                model = self.workspace.model()
                plan = bfs_program_plan(
                    model,
                    current,
                    max_nodes=self.planner_max_nodes,
                    max_depth=self.max_plan_steps,
                    legal_action_ids=current.available_actions,
                )
                if plan is None:
                    return {"ok": True, "found": False, "steps": []}
                return {
                    "ok": True,
                    "found": True,
                    "steps": [
                        {"action": {"id": step.action.id, "data": step.action.data}}
                        for step in plan
                    ],
                }
            if tool == "propose_experiment":
                action = next_explore_action(current, history)
                if action is None:
                    return {"ok": False, "error": "no legal explore action"}
                return {
                    "ok": True,
                    "action": {"id": action.id, "data": action.data},
                    "note": "commit via commit_actions with kind=exploration",
                }
            return {"ok": False, "error": f"unsupported tool {tool}"}
        except SandboxError as exc:
            metrics.backtest_failures += 1
            self.workspace.certified = False
            return {"ok": False, "error": f"sandbox: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _handle_commit(
        self,
        args: dict[str, Any],
        current: Observation,
        history: list[Transition],
    ) -> tuple[CommitRequest | None, JsonDict]:
        """校验 commit_actions：planned 需认证；exploration 仅允许单步。"""
        del history  # 保留签名与其它工具一致；动作合法性只对照 current
        raw_actions = args.get("actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            return None, {"ok": False, "error": "actions must be a non-empty list"}
        kind = str(args.get("kind", "planned"))
        if kind not in {"planned", "exploration"}:
            return None, {"ok": False, "error": "kind must be planned or exploration"}
        if kind == "planned" and not self.workspace.certified:
            return None, {
                "ok": False,
                "error": "planned commit requires certified backtest; use exploration",
            }
        if kind == "exploration" and len(raw_actions) != 1:
            return None, {"ok": False, "error": "exploration commit allows exactly one action"}
        actions: list[Action] = []
        for item in raw_actions:
            if isinstance(item, int):
                action = Action(id=int(item))
            elif isinstance(item, dict) and "id" in item:
                action = Action(id=int(item["id"]), data=dict(item.get("data", {})))
            elif isinstance(item, dict) and "action" in item and isinstance(item["action"], dict):
                nested = item["action"]
                action = Action(id=int(nested["id"]), data=dict(nested.get("data", {})))
            else:
                return None, {
                    "ok": False,
                    "error": 'each action must be {"id":N,"data":{}} or an integer id',
                }
            if action.id not in current.available_actions:
                return None, {"ok": False, "error": f"illegal action {action.id}"}
            if action.id == 0:
                return None, {
                    "ok": False,
                    "error": "action 0 (RESET) is reserved for the outer harness",
                }
            actions.append(action)
        if kind == "planned" and len(actions) > self.max_plan_steps:
            actions = actions[: self.max_plan_steps]
        return (
            CommitRequest(actions=actions, kind=kind, reason=str(args.get("reason", ""))),
            {"ok": True, "accepted": len(actions), "kind": kind},
        )


def ensure_model_predictions(
    model: ProgramWorldModel,
    before: Observation,
    action: Action,
    after: Observation,
) -> bool:
    """执行后核对：模型对 (before, action) 的预测是否与真实 after 一致。"""
    try:
        predicted = model.predict(before, action)
    except SandboxError:
        return False
    return canonical_json(predicted.snapshot()) == canonical_json(after.snapshot())
