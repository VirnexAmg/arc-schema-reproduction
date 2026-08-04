from __future__ import annotations

"""
有界 Schema 内环：理论化 → 认证 → 规划 → 提交动作。

本模块不直接操作真实环境；LLM 每轮只能返回一个 JSON 工具调用，由 DeliberationSession
在 Workspace / ProgramWorldModel 上执行，最终通过 commit_actions 把动作交给 runner。

主流程（DeliberationSession.run）：
1. 组装 system 提示 + 当前观察/历史/代码/认证状态等上下文（可选当前帧 PNG）；
2. 在 max_turns / 模型调用次数 / 花费预算内循环调用 LLM；
3. 分发工具：改代码、回测、BFS、笔记、提议探索；非法调用则反馈错误继续；
4. commit_actions 校验通过后返回 CommitRequest；done / 预算耗尽 / 达上限则无 commit。

阅读导引（文件很长，不要通读）：
- DeliberationSession.run：审议外环
- _dispatch_tool：工具分发（write_code / run_backtest / run_bfs / commit…）
- _handle_schema_cycle：Codex 一回合闭环（同步编辑 → 认证 → BFS/三选一 commit）
- _handle_commit：三种通道门禁（exploration / navigation / planned）

认证约定：run_backtest 全 Timeline 通过且 checked>0 后 workspace.certified=True；
exact 才能 BFS/planned；approximate 仅 navigation；exploration 可不认证但只能 1 步。
mismatch 后必须改码并重新认证，才能再次 planned/navigation commit。
"""

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from arc_schema.context import (
    frame_png_base64,
    frame_png_bytes,
    frame_png_manifest,
    next_explore_action,
    untried_actions,
)
from arc_schema.core import (
    Action,
    Observation,
    RunMetrics,
    Transition,
    canonical_json,
    usage_budget_reason,
)
from arc_schema.deepseek_client import ModelClient
from arc_schema.history import AppendOnlyJournal
from arc_schema.program_world_model import (
    ProgramWorldModel,
    backtest_program,
    bfs_program_plan,
    prediction_indicates_progress,
    prediction_matches,
)
from arc_schema.sandbox import SandboxError
from arc_schema.workspace import Workspace


JsonDict = dict[str, Any]


# 发给 LLM 的系统提示（保持英文，作为模型指令；勿改成中文以免改变行为）
SCHEMA_SYSTEM = """You are a Schema-style agent for an ARC-AGI-3 game.
Your primary objective is to complete as many levels as possible. Theories are
instrumental tools, not claims that must recover the hidden designer's true
mechanism. A coherent but literally wrong "key", "switch", or finite-state
interpretation is valuable if it predicts useful interactions and produces level
progress. Preserve it until evidence or lack of progress makes revision worthwhile.
You must jointly invent state grounding (objects/variables) and mechanisms.
Encode your theory ONLY as Python in world_model.py. Prefer the latent/event API:
  init_state(entry_grid) -> latent
  predict(latent, grid, action) -> (next_grid, events, next_latent)
  is_goal(latent, grid) -> bool
The legacy step(GridState, action) / is_goal(GridState) API remains supported.
For the latent/event API, grid is a list of rows. Use events LEVEL_COMPLETE,
GAME_OVER, or WIN for real boundaries. A LEVEL_COMPLETE prediction is checked
against level progress; the environment supplies the unseen next-level entry grid.
Helpers available inside the sandbox: GridState, find_color, bbox, neighbors4,
crop_frame, rotate90, connected_components, deepcopy, np (NumPy).
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
planning. If last_mismatch is present, revise representation or rules to explain it
BEFORE any planned or navigation commit_actions.
When multiple rules fit history, use propose_experiment with a legal candidate
action and at least two competing, named predictions. The returned experiment_id
binds the subsequent exploration commit to that exact action.

Working memory (required for mechanism discovery):
- hypotheses.json is the authoritative structured theory ledger. Use
  update_hypotheses to create stable H_<name> IDs before proposing an experiment.
  Canonical statuses are active, supported, rejected, and uncertain. The protocol
  transparently normalizes confirmed to supported and audits that normalization;
  every other unknown status is rejected.
  An ID denotes a continuing line of thought: you may revise its statement as later
  levels refine the interpretation; the harness preserves prior statements.
  Review observed experiments when decision-relevant, but do not delay a promising
  goal-directed plan merely to make the ledger tidy.
- Keep notes.md as a readable synthesis of: grounded objects, the stable ledger
  hypotheses, what experiments ruled out, and what still needs testing.
- Prefer write_notes when your hypothesis changes — do not leave notes empty.
- Coordinate shortcuts that only memorize one level-up cell are weak theories;
  prefer reusable mechanisms that transfer across levels.
- When small panels/glyphs repeat, test compact object-level transform families
  (translation, rotation, reflection, recoloring, permutation) before inventing
  long coordinate-specific finite-state sequences. This is a generic ARC prior,
  not permission to assume any particular transform.
- Source line/AST/branch targets are soft compression guidance. Exceeding them is
  acceptable when the model remains predictive and helps progress. Hard audit
  rejection is reserved for extreme growth or trajectory-sized literal lookup.

CRITICAL efficiency rules:
- With little Timeline evidence, prefer commit_actions kind=exploration SOON
  (often within the first 2-4 tool turns) instead of endless rewrite loops.
- At most a couple of write_code/apply_patch attempts per deliberation before
  either run_backtest+commit or a single explore commit.
- Do not spend the whole turn budget only rewriting code.
- Prefer propose_experiment then commit_actions over another full rewrite.
- Exploitation is first-class: if a certified model offers a plausible path to
  level progress, run_bfs and commit it before doing optional theory cleanup.
- Not every useful action is a formal discriminating experiment. Navigation,
  opportunistic probing, and executing an approximate but useful model are allowed.
- Use kind=navigation for a coherent 2-16 action route that advances toward an
  interaction or subgoal even when the final level goal is not yet modeled. Navigation
  requires a certified model but not a BFS plan_id; the harness predicts and checks
  every step and stops the burst on any mismatch, level boundary, or terminal state.
- Once movement is certified, bundle deterministic multi-step travel as navigation
  instead of spending one model call per tile. Do not use navigation to bypass an
  available BFS plan: if predict() can reach is_goal(), it must emit LEVEL_COMPLETE
  or WIN on that same transition so the route can be certified as planned progress.
- Exploration is exactly one action. Never submit a multi-action exploration commit.
- After run_bfs returns found=false, obey bfs_advisory and do not repeat it during
  cooldown unless world_model.py is revised. Use navigation or one-step exploration.

Vision: when a PNG of the current frame is provided, use it together with the
JSON/RLE context for grounding objects. Do not ignore the image.

Tools (deliberation does not touch the real environment):
- write_code / apply_patch: edit world_model.py
- run_backtest: replay step() on the FULL Timeline (must pass with checked>0 before planning)
- run_bfs: search inside a certified model for real level progress; returns a plan_id
- write_notes / read_notes: persistent working memory
- update_hypotheses: create stable theories or update their evidence/status
- propose_experiment: register one falsifiable, action-bound experiment
- commit_actions: the ONLY channel that executes real environment actions
- schema_cycle: preferred coding-agent closeout. After native workspace edits,
  the harness automatically runs full backtest, tries exact-certified BFS, and
  otherwise validates a monitored navigation route or one exploration action.

Return one JSON object per turn with EXACT schemas:
{"tool":"write_code","args":{"source":"<full world_model.py text>"}}
{"tool":"apply_patch","args":{"old":"<unique old snippet>","new":"<replacement>"}}
{"tool":"run_backtest","args":{}}
{"tool":"run_bfs","args":{}}
{"tool":"write_notes","args":{"text":"..."}}
{"tool":"read_notes","args":{}}
{"tool":"update_hypotheses","args":{"hypotheses":[{"id":"H_transform","statement":"...","status":"active"},{"id":"H_sequence","statement":"...","status":"active"}],"evidence_seq":[1,2],"reason":"...","experiment_id":"<optional observed experiment being reviewed>"}}
{"tool":"propose_experiment","args":{"action":{"id":2,"data":{}},"hypotheses":[{"id":"H_transform","prediction":"..."},{"id":"H_sequence","prediction":"..."}],"rationale":"...","evidence_seq":[1,2]}}
{"tool":"commit_actions","args":{"kind":"planned","plan_id":"<from run_bfs>","actions":[{"id":1,"data":{}}],"rationale":"...","evidence_seq":[1,2]}}
{"tool":"commit_actions","args":{"kind":"navigation","actions":[{"id":1,"data":{}},{"id":4,"data":{}}],"rationale":"certified route toward a useful interaction","evidence_seq":[1,2]}}
{"tool":"commit_actions","args":{"kind":"exploration","experiment_id":"<optional from propose_experiment>","actions":[{"id":1,"data":{}}],"rationale":"...","evidence_seq":[1,2]}}
{"tool":"schema_cycle","args":{"strategy":"auto","workspace_edits":{"patch":{"old":"<unique old snippet>","new":"<replacement>"},"notes_text":"..."},"hypothesis_updates":{"hypotheses":[{"id":"H_transform","statement":"...","status":"active"}],"evidence_seq":[1,2],"reason":"..."},"navigation_actions":[{"id":1,"data":{}},{"id":4,"data":{}}],"exploration_action":{"id":2,"data":{}},"decision_record":{"hypotheses":["H_transform"],"evidence_seq":[1,2],"expected_observation":"...","revision_trigger":"..."},"rationale":"..."}}
{"tool":"done","args":{"reason":"..."}}

In step()/predict(), action is a dict: use int(action["id"]), not action == 1.
Do not commit action id 0 (RESET); the outer harness handles life resets.
"""


WORKSPACE_NATIVE_ADDENDUM = """

WORKSPACE-NATIVE CODEX OVERRIDE:
- The complete current snapshot, recent transitions, world_model.py, notes, ledger,
  and current frame are already supplied in this request. Do not launch PowerShell,
  cmd, bash, terminal commands, subprocesses, or recursive workspace enumeration.
- Use native apply_patch/file tools before your final response. If a native file or
  image viewer is unavailable, use the supplied JSON/RLE/PNG context and return a
  schema_cycle workspace_edits fallback; do not retry through a shell.
- Your final JSON MUST be schema_cycle or done. The standalone JSON write_code,
  apply_patch, and write_notes schemas above exist only for chat_json compatibility.
- If native file tools are unavailable, include workspace_edits in schema_cycle.
  workspace_edits may contain exactly one of source or patch={old,new}, plus
  notes_text. Include notes_text whenever evidence changed the working theory.
- Use schema_cycle.hypothesis_updates to atomically keep hypotheses.json aligned
  with decision_record and notes; do not leave named hypotheses only in prose.
- In one final schema_cycle, provide the next legal exploration_action as a fallback
  even after editing, so replay/search/commit can close without another model call.
"""


TOOL_NAMES = {
    "write_code",
    "apply_patch",
    "run_backtest",
    "run_bfs",
    "write_notes",
    "read_notes",
    "update_hypotheses",
    "propose_experiment",
    "commit_actions",
    "schema_cycle",
    "done",
}


@dataclass
class CommitRequest:
    """内环结束时交给 runner 在真实环境执行的动作包。"""

    actions: list[Action]
    kind: str  # "planned" | "navigation" | "exploration"
    reason: str = ""
    plan_id: str | None = None
    experiment_id: str | None = None
    rationale: str = ""
    evidence_seq: tuple[int, ...] = ()


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


def _user_content_with_optional_vision(
    payload: JsonDict,
    current: Observation,
    *,
    vision_enabled: bool,
) -> str | list[dict[str, Any]]:
    """Initial deliberation user message: JSON context, optionally plus current-frame PNG."""
    text = canonical_json(payload)
    if not vision_enabled:
        return text
    png = frame_png_base64(current)
    return [
        {
            "type": "text",
            "text": (
                "Current frame as PNG. Use it together with the JSON context for "
                "state grounding. JSON follows.\n" + text
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{png}"},
        },
    ]


def _reasoning_payload(response: Any) -> JsonDict:
    return {
        "reasoning_text": getattr(response, "reasoning_text", None),
        "reasoning_status": getattr(response, "reasoning_status", "absent"),
        "reasoning_tokens": int(getattr(response.usage, "reasoning_tokens", 0) or 0),
    }


def _accumulate_codex_runtime(metrics: RunMetrics, stats: JsonDict) -> None:
    metrics.codex_transport_reconnects += int(stats.get("transport_reconnects", 0))
    metrics.codex_https_fallbacks += int(stats.get("https_fallbacks", 0))
    metrics.codex_transport_timeouts += int(stats.get("transport_timeouts", 0))
    metrics.codex_turn_failures += int(stats.get("turn_failures", 0))
    metrics.codex_tool_failures += int(stats.get("tool_failures", 0))
    metrics.codex_post_completion_forced_exits += int(stats.get("post_completion_forced_exits", 0))


class DeliberationSession:
    """有界 Schema 内环：理论化 → 认证 → 规划 → 提交（不直接 step 环境）。"""

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
        spend_reserve_usd: float = 0.0,
        vision_enabled: bool = False,
        env_actions_so_far: int = 0,
        allow_approximate_visual_matches: bool = False,
        max_total_tokens: int = 0,
        max_uncached_tokens: int = 0,
        max_output_tokens: int = 0,
        token_reserve_per_call: int = 0,
        max_notional_cost_usd: float = 0.0,
    ) -> None:
        self.client = client
        self.workspace = workspace
        self.max_turns = max_turns
        self.planner_max_nodes = planner_max_nodes
        self.max_plan_steps = max_plan_steps
        self.max_model_calls = max_model_calls
        self.max_spend_usd = max_spend_usd
        self.spend_reserve_usd = max(0.0, spend_reserve_usd)
        self.vision_enabled = vision_enabled
        self.env_actions_so_far = env_actions_so_far
        self.allow_approximate_visual_matches = allow_approximate_visual_matches
        self.max_total_tokens = max(0, max_total_tokens)
        self.max_uncached_tokens = max(0, max_uncached_tokens)
        self.max_output_tokens = max(0, max_output_tokens)
        self.token_reserve_per_call = max(0, token_reserve_per_call)
        self.max_notional_cost_usd = max(0.0, max_notional_cost_usd)
        self._pending_plan: JsonDict | None = None
        self._pending_experiment: JsonDict | None = None
        self._code_edits_this_session = 0

    def run(
        self,
        current: Observation,
        history: list[Transition],
        journal: AppendOnlyJournal,
        metrics: RunMetrics,
    ) -> DeliberationResult:
        """跑一轮审议：循环调用模型与工具，直到 commit / done / 预算耗尽。"""
        """运行多轮工具循环，直到 commit / done / 预算或轮次耗尽。"""
        tool_trace: list[JsonDict] = []
        begin = getattr(self.client, "begin_deliberation", None)
        rollover = begin() if callable(begin) else None
        if rollover is not None:
            metrics.codex_session_rollovers += 1
            journal.append(
                "codex_session_rollover",
                {
                    "env_step": self.env_actions_so_far,
                    **rollover,
                },
            )
        self._pending_experiment = self.workspace.pending_experiment(current.fingerprint)
        context = self._context_payload(current, history)
        if self.vision_enabled:
            png = frame_png_bytes(current)
            manifest = frame_png_manifest(current)
            vision_path = (
                self.workspace.vision_frames_dir
                / f"env-{self.env_actions_so_far:04d}-{current.fingerprint[:12]}.png"
            )
            if not vision_path.exists():
                vision_path.write_bytes(png)
            context["vision_frame"] = {**manifest, "path": str(vision_path)}
            journal.append(
                "vision_frame",
                {
                    "env_step": self.env_actions_so_far,
                    **manifest,
                    "path": str(vision_path),
                },
            )
        context_chars = len(canonical_json(context))
        metrics.max_deliberation_context_chars = max(
            metrics.max_deliberation_context_chars,
            context_chars,
        )
        system_content = SCHEMA_SYSTEM
        if getattr(self.client, "workspace_native", False):
            system_content += WORKSPACE_NATIVE_ADDENDUM
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": _user_content_with_optional_vision(
                    context,
                    current,
                    vision_enabled=self.vision_enabled,
                ),
            },
        ]
        journal.append(
            "deliberation_started",
            {
                "env_step": self.env_actions_so_far,
                "timeline_len": len(history),
                "vision_enabled": self.vision_enabled,
                "certified": self.workspace.certified,
                "mismatch_blocks_planning": self.workspace.mismatch_blocks_planning,
                "wm_version": self.workspace.version,
                "notes_version": self.workspace.notes_version,
                "hypothesis_version": self.workspace.hypothesis_version,
                "context_chars": context_chars,
                "hypothesis_context_chars": context["hypothesis_ledger"].get("context_chars", 0),
                "pending_experiment_id": (
                    self._pending_experiment.get("experiment_id")
                    if self._pending_experiment is not None
                    else None
                ),
            },
        )
        for turn in range(self.max_turns):
            if metrics.model_calls >= self.max_model_calls:
                return DeliberationResult(None, tool_trace, "model_call_budget")
            resource_stop = usage_budget_reason(
                metrics.usage,
                max_total_tokens=self.max_total_tokens,
                max_uncached_tokens=self.max_uncached_tokens,
                max_output_tokens=self.max_output_tokens,
                max_notional_cost_usd=self.max_notional_cost_usd,
                total_token_reserve=self.token_reserve_per_call,
            )
            if resource_stop is not None:
                return DeliberationResult(None, tool_trace, resource_stop)
            spent = metrics.usage.estimated_cost_usd or 0.0
            if self.max_spend_usd > 0 and (
                spent >= self.max_spend_usd or spent + self.spend_reserve_usd > self.max_spend_usd
            ):
                return DeliberationResult(None, tool_trace, "spend_budget")
            metrics.model_calls += 1
            # Log text-only request summary to avoid dumping huge base64 into the journal.
            log_messages = []
            for message in messages[-2:]:
                content = message.get("content")
                if isinstance(content, list):
                    log_messages.append(
                        {
                            "role": message.get("role"),
                            "content": "[multipart: text+image omitted from journal]",
                            "has_image": any(
                                isinstance(part, dict) and part.get("type") == "image_url"
                                for part in content
                            ),
                        }
                    )
                else:
                    log_messages.append(message)
            journal.append(
                "model_request",
                {
                    "purpose": "deliberation",
                    "env_step": self.env_actions_so_far,
                    "turn": turn,
                    "messages": log_messages,
                },
            )
            try:
                response = self.client.complete_json(messages, "deliberation")
            except Exception as exc:
                metrics.model_failures += 1
                metrics.model_api_attempts += int(getattr(exc, "attempts", 0))
                error_usage = getattr(exc, "usage", None)
                if error_usage is not None:
                    metrics.usage.add(error_usage)
                runtime_stats = dict(getattr(self.client, "last_event_stats", {}) or {})
                _accumulate_codex_runtime(metrics, runtime_stats)
                failure_kind = str(getattr(self.client, "last_failure_kind", "") or "")
                external = self.workspace.sync_external_changes()
                if external["code_changed"]:
                    journal.append(
                        "wm_revision",
                        {
                            "env_step": self.env_actions_so_far,
                            "version": external["wm_version"],
                            "wm_version": external["wm_version"],
                            "method": "workspace_native_edit_after_model_error",
                        },
                    )
                if external["notes_changed"]:
                    journal.append(
                        "notes_revision",
                        {
                            "env_step": self.env_actions_so_far,
                            "notes_version": external["notes_version"],
                            "method": "workspace_native_edit_after_model_error",
                        },
                    )
                journal.append(
                    "model_error",
                    {
                        "purpose": "deliberation",
                        "env_step": self.env_actions_so_far,
                        "turn": turn,
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "api_attempts": int(getattr(exc, "attempts", 0)),
                        "failure_kind": failure_kind or "model_error",
                        "codex_runtime": runtime_stats,
                        "workspace_sync_error": external.get("code_error"),
                    },
                )
                if failure_kind == "infrastructure_error":
                    return DeliberationResult(
                        None,
                        tool_trace,
                        "infrastructure_error",
                    )
                return DeliberationResult(None, tool_trace, f"model_error:{exc}")
            metrics.model_api_attempts += response.attempts
            metrics.usage.add(response.usage)
            metrics.max_codex_prompt_tokens_per_turn = max(
                metrics.max_codex_prompt_tokens_per_turn,
                int(response.usage.prompt_tokens),
            )
            runtime_stats = dict(getattr(self.client, "last_event_stats", {}) or {})
            _accumulate_codex_runtime(metrics, runtime_stats)
            external = self.workspace.sync_external_changes()
            if external["code_changed"]:
                journal.append(
                    "wm_revision",
                    {
                        "env_step": self.env_actions_so_far,
                        "version": external["wm_version"],
                        "wm_version": external["wm_version"],
                        "method": "workspace_native_edit",
                    },
                )
            if external["notes_changed"]:
                journal.append(
                    "notes_revision",
                    {
                        "env_step": self.env_actions_so_far,
                        "notes_version": external["notes_version"],
                        "method": "workspace_native_edit",
                    },
                )
            reasoning = _reasoning_payload(response)
            journal.append(
                "model_response",
                {
                    "purpose": "deliberation",
                    "env_step": self.env_actions_so_far,
                    "turn": turn,
                    "raw_text": response.raw_text,
                    "parsed": response.value,
                    "usage": asdict(response.usage),
                    "latency_seconds": response.latency_seconds,
                    "api_attempts": response.attempts,
                    "model_thread_id": getattr(self.client, "thread_id", None),
                    "native_trace_path": (
                        str(self.workspace.root / "codex-cli-events.jsonl")
                        if getattr(self.client, "workspace_native", False)
                        else None
                    ),
                    "codex_runtime": runtime_stats,
                    **reasoning,
                },
            )
            resource_stop = usage_budget_reason(
                metrics.usage,
                max_total_tokens=self.max_total_tokens,
                max_uncached_tokens=self.max_uncached_tokens,
                max_output_tokens=self.max_output_tokens,
                max_notional_cost_usd=self.max_notional_cost_usd,
            )
            if resource_stop is not None:
                return DeliberationResult(None, tool_trace, resource_stop)
            if external.get("code_error"):
                observation = {
                    "ok": False,
                    "error": (
                        "Direct world_model.py edit was rejected and restored: "
                        f"{external['code_error']}"
                    ),
                }
                tool_trace.append({"tool": "workspace_sync", "args": {}, "result": observation})
                journal.append("deliberation_tool", tool_trace[-1])
                messages.append({"role": "assistant", "content": response.raw_text})
                messages.append({"role": "user", "content": canonical_json(observation)})
                continue
            if (
                self.max_spend_usd > 0
                and (metrics.usage.estimated_cost_usd or 0.0) >= self.max_spend_usd
            ):
                return DeliberationResult(None, tool_trace, "spend_budget")
            try:
                tool, args = _parse_tool_call(response.value)
            except Exception as exc:
                observation = {"ok": False, "error": f"bad tool call: {exc}"}
                tool_trace.append(
                    {"tool": "invalid", "args": response.value, "result": observation}
                )
                journal.append(
                    "deliberation_turn",
                    {
                        "env_step": self.env_actions_so_far,
                        "turn": turn,
                        "tool": "invalid",
                        "ok": False,
                        "error": str(exc),
                    },
                )
                messages.append({"role": "assistant", "content": response.raw_text})
                messages.append({"role": "user", "content": canonical_json(observation)})
                continue

            if tool == "done":
                tool_trace.append({"tool": tool, "args": args, "result": {"ok": True}})
                journal.append(
                    "deliberation_turn",
                    {
                        "env_step": self.env_actions_so_far,
                        "turn": turn,
                        "tool": tool,
                        "ok": True,
                        "reason": str(args.get("reason", "done")),
                    },
                )
                return DeliberationResult(None, tool_trace, str(args.get("reason", "done")))

            if tool == "schema_cycle":
                commit, observation = self._handle_schema_cycle(
                    args,
                    current,
                    history,
                    metrics,
                    journal,
                )
                tool_trace.append({"tool": tool, "args": args, "result": observation})
                journal.append("deliberation_tool", tool_trace[-1])
                journal.append(
                    "deliberation_turn",
                    {
                        "env_step": self.env_actions_so_far,
                        "turn": turn,
                        "tool": tool,
                        "ok": bool(observation.get("ok")),
                        "selected_kind": observation.get("selected_kind"),
                        "plan_id": observation.get("plan_id"),
                        "decision_record": observation.get("decision_record"),
                        "error": observation.get("error"),
                    },
                )
                if commit is not None:
                    return DeliberationResult(commit, tool_trace, "compound_commit")
                messages.append({"role": "assistant", "content": response.raw_text})
                messages.append({"role": "user", "content": canonical_json(observation)})
                continue

            if tool == "commit_actions":
                commit, observation = self._handle_commit(args, current, history)
                tool_trace.append({"tool": tool, "args": args, "result": observation})
                journal.append("deliberation_tool", tool_trace[-1])
                journal.append(
                    "deliberation_turn",
                    {
                        "env_step": self.env_actions_so_far,
                        "turn": turn,
                        "tool": tool,
                        "ok": bool(observation.get("ok")),
                        "kind": args.get("kind"),
                        "accepted": observation.get("accepted"),
                        "plan_id": observation.get("plan_id"),
                        "experiment_id": observation.get("experiment_id"),
                        "rationale": str(args.get("rationale", ""))[:1000],
                        "evidence_seq": args.get("evidence_seq", []),
                        "error": observation.get("error"),
                    },
                )
                if commit is not None:
                    return DeliberationResult(commit, tool_trace, "commit")
                messages.append({"role": "assistant", "content": response.raw_text})
                messages.append({"role": "user", "content": canonical_json(observation)})
                continue

            observation = self._dispatch_tool(tool, args, current, history, metrics, journal)
            tool_trace.append({"tool": tool, "args": args, "result": observation})
            journal.append("deliberation_tool", tool_trace[-1])
            journal.append(
                "deliberation_turn",
                {
                    "env_step": self.env_actions_so_far,
                    "turn": turn,
                    "tool": tool,
                    "ok": bool(observation.get("ok", True)),
                    "version": observation.get("version"),
                    "notes_version": observation.get("notes_version"),
                    "certified": observation.get("certified"),
                    "plan_id": observation.get("plan_id"),
                    "experiment_id": observation.get("experiment_id"),
                    "rationale": str(args.get("rationale", ""))[:1000],
                    "evidence_seq": args.get("evidence_seq", []),
                    "error": observation.get("error"),
                },
            )
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
        instruction = (
            "If timeline_len is small, commit one exploration action quickly. "
            "Prefer apply_patch + run_backtest, then either run_bfs+commit_actions "
            "(only if certified with checked>0), commit a monitored navigation burst "
            "toward a useful subgoal, or commit a single explore action. "
            "After level-up or life_reset, re-certify before trusting old plans. "
            "Use hypotheses.json to preserve useful evolving interpretations. "
            "Level progress outranks theory tidiness: exploit a plausible certified "
            "plan before optional experiment review. Update notes.md as a readable "
            "synthesis. Do not loop on write_code without acting."
        )
        unresolved = self.workspace.unresolved_observed_experiments()
        if unresolved:
            instruction = (
                "EXPERIMENT OUTCOME AVAILABLE: review it with update_hypotheses when "
                "it changes the next decision. It does not block BFS, navigation, or "
                "a higher-value experiment. " + instruction
            )
        if self.workspace.mismatch_blocks_planning:
            instruction = (
                f"BLOCKED ({self.workspace.planning_block_reason}): "
                f"world_model version must reach >=v{self.workspace.required_revision_version} "
                "and run_backtest must pass with checked>0 before any planned or "
                "navigation commit. "
                "For a prediction_mismatch this requires a real code revision. "
                "Exploration is still allowed. Also write_notes with what was falsified. "
                + instruction
            )
        bfs_advisory = self.workspace.bfs_advisory(
            level=current.levels_completed,
            env_step=self.env_actions_so_far,
        )
        if not bfs_advisory["available"]:
            instruction = (
                "BFS NO-PLAN COOLDOWN: do not call run_bfs now. Use a certified "
                "navigation burst, revise world_model.py, or take one exploration "
                "action. " + instruction
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
            "world_model_complexity": self.workspace.model_complexity(),
            "world_model_complexity_warnings": (self.workspace.model_complexity_warnings()),
            "notes_md": self.workspace.read_notes()[:4000],
            "hypothesis_ledger": self.workspace.hypothesis_context(),
            "bfs_advisory": bfs_advisory,
            "certified": self.workspace.certified,
            "certified_exact": self.workspace.certified_exact,
            "mismatch_blocks_planning": self.workspace.mismatch_blocks_planning,
            "planning_block_reason": self.workspace.planning_block_reason,
            "required_revision_version": self.workspace.required_revision_version,
            "wm_version": self.workspace.version,
            "notes_version": self.workspace.notes_version,
            "last_backtest": (
                asdict(self.workspace.last_backtest)
                if self.workspace.last_backtest is not None
                else None
            ),
            "last_mismatch": self.workspace.last_mismatch,
            "vision_enabled": self.vision_enabled,
            "instruction": instruction,
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
        try:
            if tool == "write_code":
                if self._code_edits_this_session >= 4:
                    return {
                        "ok": False,
                        "error": (
                            "four world-model edits already occurred in this "
                            "deliberation; act or start a fresh evidence-driven round"
                        ),
                    }
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
                self._code_edits_this_session += 1
                self._pending_plan = None
                journal.append(
                    "wm_revision",
                    {
                        "env_step": self.env_actions_so_far,
                        "version": self.workspace.version,
                        "kind": "write_code",
                        "path": str(
                            self.workspace.wm_versions_dir / f"v{self.workspace.version:04d}.py"
                        ),
                    },
                )
                return {
                    "ok": True,
                    "version": self.workspace.version,
                    "certified": False,
                    "complexity": self.workspace.model_complexity(),
                    "complexity_warnings": (self.workspace.model_complexity_warnings()),
                    "message": "code written; run_backtest required before planning",
                }
            if tool == "apply_patch":
                if self._code_edits_this_session >= 4:
                    return {
                        "ok": False,
                        "error": (
                            "four world-model edits already occurred in this "
                            "deliberation; act or start a fresh evidence-driven round"
                        ),
                    }
                old = str(args.get("old", ""))
                new = str(args.get("new", ""))
                if not old:
                    return {"ok": False, "error": "apply_patch requires unique args.old"}
                self.workspace.apply_patch(old, new)
                self._code_edits_this_session += 1
                self._pending_plan = None
                journal.append(
                    "wm_revision",
                    {
                        "env_step": self.env_actions_so_far,
                        "version": self.workspace.version,
                        "kind": "apply_patch",
                        "path": str(
                            self.workspace.wm_versions_dir / f"v{self.workspace.version:04d}.py"
                        ),
                    },
                )
                return {
                    "ok": True,
                    "version": self.workspace.version,
                    "certified": False,
                    "complexity": self.workspace.model_complexity(),
                    "complexity_warnings": (self.workspace.model_complexity_warnings()),
                    "message": "patch applied; run_backtest required before planning",
                }
            if tool == "update_hypotheses":
                raw_items = args.get("hypotheses")
                if not isinstance(raw_items, list):
                    return {
                        "ok": False,
                        "error": "update_hypotheses requires args.hypotheses list",
                    }
                raw_evidence = args.get("evidence_seq", [])
                if not isinstance(raw_evidence, list):
                    raw_evidence = []
                evidence_seq = [int(value) for value in raw_evidence if isinstance(value, int)][
                    :100
                ]
                reason = str(args.get("reason", "")).strip()
                experiment_id = str(args.get("experiment_id", "")).strip() or None
                result = self.workspace.update_hypotheses(
                    raw_items,
                    evidence_seq=evidence_seq,
                    reason=reason,
                    experiment_id=experiment_id,
                )
                metrics.hypothesis_revisions += 1
                if experiment_id is not None:
                    metrics.experiments_resolved += 1
                journal.append(
                    "hypothesis_revision",
                    {
                        "env_step": self.env_actions_so_far,
                        **result,
                        "reason": reason[:1000],
                        "path": str(self.workspace.hypothesis_ledger_path),
                    },
                )
                return {"ok": True, **result}
            if tool == "write_notes":
                version = self.workspace.write_notes(str(args.get("text", "")))
                journal.append(
                    "notes_revision",
                    {
                        "env_step": self.env_actions_so_far,
                        "notes_version": version,
                        "chars": len(str(args.get("text", ""))),
                        "text_preview": str(args.get("text", ""))[:500],
                    },
                )
                return {"ok": True, "notes_version": version}
            if tool == "read_notes":
                return {
                    "ok": True,
                    "text": self.workspace.read_notes(),
                    "notes_version": self.workspace.notes_version,
                }
            if tool == "run_backtest":
                model = self.workspace.model()
                result = backtest_program(
                    model,
                    history,
                    allow_approximate=self.allow_approximate_visual_matches,
                )
                self.workspace.last_backtest = result
                # Vacuous green (no gameplay transitions checked) cannot certify.
                revision_gate_ok = (
                    not self.workspace.mismatch_blocks_planning
                    or self.workspace.version >= self.workspace.required_revision_version
                )
                if result.passed and result.checked > 0 and revision_gate_ok:
                    self.workspace.certified = True
                    self.workspace.certified_exact = result.approximate_matches == 0
                    if self.workspace.mismatch_blocks_planning:
                        self.workspace.clear_mismatch_block()
                        self.workspace.last_mismatch = None
                else:
                    self.workspace.certified = False
                    self.workspace.certified_exact = False
                if not result.passed:
                    metrics.backtest_failures += 1
                payload = {
                    "ok": True,
                    "result": asdict(result),
                    "certified": self.workspace.certified,
                    "certified_exact": self.workspace.certified_exact,
                }
                if result.passed and result.checked == 0:
                    payload["warning"] = (
                        "vacuous backtest (checked=0): cannot certify or plan; "
                        "gather exploration transitions first"
                    )
                if result.passed and result.approximate_matches > 0:
                    payload["instrumental_note"] = (
                        f"{result.approximate_matches}/{result.checked} transitions "
                        "have only small non-terminal visual differences. The model "
                        "may still be used for monitored navigation, but exact "
                        "certification is required for BFS planning; predicted level, "
                        "WIN, GAME_OVER and action-space changes remain strict."
                    )
                if result.passed and result.checked > 0 and not revision_gate_ok:
                    payload["warning"] = (
                        "backtest passed but planning remains blocked: create a new "
                        f"world-model revision (need >=v{self.workspace.required_revision_version})"
                    )
                return payload
            if tool == "run_bfs":
                if not self.workspace.certified:
                    return {
                        "ok": False,
                        "error": "run_bfs requires a certified world model (checked>0)",
                    }
                if self.workspace.mismatch_blocks_planning:
                    return {
                        "ok": False,
                        "error": "run_bfs blocked until mismatch is revised and re-certified",
                    }
                if not self.workspace.certified_exact:
                    return {
                        "ok": False,
                        "error": (
                            "run_bfs requires exact full-Timeline certification; "
                            "approximate certification is navigation-only"
                        ),
                    }
                advisory = self.workspace.bfs_advisory(
                    level=current.levels_completed,
                    env_step=self.env_actions_so_far,
                )
                if not advisory["available"]:
                    self._pending_plan = None
                    metrics.bfs_no_plan_cache_hits += 1
                    journal.append(
                        "bfs_no_plan_cached",
                        {
                            "env_step": self.env_actions_so_far,
                            "wm_version": self.workspace.version,
                            "level": current.levels_completed,
                            **advisory,
                        },
                    )
                    return {
                        "ok": True,
                        "found": False,
                        "cached": True,
                        "steps": [],
                        "bfs_advisory": advisory,
                        "instruction": (
                            "Do not retry BFS during cooldown. Use kind=navigation "
                            "for a certified subgoal route or explore one action."
                        ),
                    }
                model = self.workspace.model()
                plan = bfs_program_plan(
                    model,
                    current,
                    max_nodes=self.planner_max_nodes,
                    max_depth=self.max_plan_steps,
                    legal_action_ids=current.available_actions,
                    history=history,
                )
                if plan is None:
                    self._pending_plan = None
                    self.workspace.record_bfs_no_plan(
                        level=current.levels_completed,
                        env_step=self.env_actions_so_far,
                    )
                    metrics.bfs_no_plan_results += 1
                    journal.append(
                        "bfs_no_plan",
                        {
                            "env_step": self.env_actions_so_far,
                            "wm_version": self.workspace.version,
                            "level": current.levels_completed,
                            "reason": "search_exhausted",
                        },
                    )
                    return {
                        "ok": True,
                        "found": False,
                        "cached": False,
                        "steps": [],
                        "instruction": (
                            "Use kind=navigation for a certified route toward an "
                            "interaction; do not repeat BFS until cooldown expires "
                            "or the world model changes."
                        ),
                    }
                if not plan:
                    self._pending_plan = None
                    self.workspace.record_bfs_no_plan(
                        level=current.levels_completed,
                        env_step=self.env_actions_so_far,
                    )
                    metrics.bfs_no_plan_results += 1
                    return {
                        "ok": True,
                        "found": False,
                        "steps": [],
                        "error": (
                            "model marks the current state as goal without new level "
                            "progress; revise is_goal"
                        ),
                    }
                runtime = model.runtime_from_history(current, history)
                progress = False
                for step in plan:
                    prediction = model.predict_runtime(runtime, step.action)
                    progress = progress or prediction_indicates_progress(prediction)
                    runtime = prediction.next_runtime
                if not progress and not (
                    runtime.observation.state == "WIN"
                    or runtime.observation.levels_completed > current.levels_completed
                ):
                    self._pending_plan = None
                    self.workspace.record_bfs_no_plan(
                        level=current.levels_completed,
                        env_step=self.env_actions_so_far,
                    )
                    metrics.bfs_no_plan_results += 1
                    return {
                        "ok": True,
                        "found": False,
                        "steps": [],
                        "error": "BFS target does not predict level progress or WIN",
                    }
                action_payloads = [
                    {"id": step.action.id, "data": step.action.data} for step in plan
                ]
                binding = {
                    "wm_version": self.workspace.version,
                    "current_fingerprint": current.fingerprint,
                    "actions": action_payloads,
                }
                plan_id = hashlib.sha256(canonical_json(binding).encode()).hexdigest()[:20]
                self._pending_plan = {**binding, "plan_id": plan_id}
                self.workspace.clear_bfs_no_plan()
                metrics.bfs_plans_generated += 1
                journal.append(
                    "bfs_plan_created",
                    {
                        "env_step": self.env_actions_so_far,
                        "plan_id": plan_id,
                        "wm_version": self.workspace.version,
                        "current_fingerprint": current.fingerprint,
                        "actions": action_payloads,
                    },
                )
                return {
                    "ok": True,
                    "found": True,
                    "plan_id": plan_id,
                    "steps": [
                        {"action": {"id": step.action.id, "data": step.action.data}}
                        for step in plan
                    ],
                    "commit_instruction": (
                        "commit_actions kind=planned must include this plan_id and "
                        "the exact returned action sequence"
                    ),
                }
            if tool == "propose_experiment":
                raw_action = args.get("action")
                if isinstance(raw_action, int):
                    action = Action(id=int(raw_action))
                elif isinstance(raw_action, dict) and "id" in raw_action:
                    action = Action(
                        id=int(raw_action["id"]),
                        data=dict(raw_action.get("data", {})),
                    )
                else:
                    action = next_explore_action(current, history)
                if action is None or action.id not in current.available_actions or action.id == 0:
                    return {"ok": False, "error": "a legal non-RESET experiment action is required"}
                hypotheses = args.get("hypotheses")
                if not isinstance(hypotheses, list):
                    hypotheses = []
                normalized: list[JsonDict] = []
                for index, item in enumerate(hypotheses[:6]):
                    if isinstance(item, dict):
                        hypothesis_id = str(item.get("id", f"H{index + 1}")).strip()
                        prediction = str(item.get("prediction", "")).strip()
                    else:
                        hypothesis_id = f"H{index + 1}"
                        prediction = str(item).strip()
                    if hypothesis_id and prediction:
                        normalized.append({"id": hypothesis_id, "prediction": prediction[:1000]})
                if len(normalized) < 2:
                    return {
                        "ok": False,
                        "error": (
                            "propose_experiment requires at least two named hypotheses "
                            "with distinct predicted outcomes"
                        ),
                    }
                if len({item["prediction"] for item in normalized}) < 2:
                    return {
                        "ok": False,
                        "error": "hypotheses must predict different observable outcomes",
                    }
                if len({item["id"] for item in normalized}) != len(normalized):
                    return {
                        "ok": False,
                        "error": "experiment hypothesis IDs must be distinct",
                    }
                rationale = str(args.get("rationale", "")).strip()
                raw_evidence = args.get("evidence_seq", [])
                if not isinstance(raw_evidence, list):
                    raw_evidence = []
                evidence_seq = [int(value) for value in raw_evidence if isinstance(value, int)][:20]
                binding = {
                    "current_fingerprint": current.fingerprint,
                    "action": {"id": action.id, "data": action.data},
                    "hypotheses": normalized,
                    "rationale": rationale[:1000],
                    "evidence_seq": evidence_seq,
                }
                experiment_id = (
                    "exp-" + hashlib.sha256(canonical_json(binding).encode()).hexdigest()[:16]
                )
                pending_experiment = {
                    **binding,
                    "experiment_id": experiment_id,
                }
                hypothesis_version = self.workspace.register_experiment(pending_experiment)
                self._pending_experiment = pending_experiment
                metrics.discriminating_experiments += 1
                journal.append(
                    "experiment_proposed",
                    {
                        "env_step": self.env_actions_so_far,
                        "experiment_id": experiment_id,
                        "hypothesis_version": hypothesis_version,
                        **binding,
                    },
                )
                return {
                    "ok": True,
                    "experiment_id": experiment_id,
                    "action": {"id": action.id, "data": action.data},
                    "hypotheses": normalized,
                    "hypothesis_version": hypothesis_version,
                    "rationale": rationale[:1000],
                    "evidence_seq": evidence_seq,
                    "note": (
                        "Commit this exact action via kind=exploration with the "
                        "experiment_id. Then write_notes with what the observed "
                        "outcome ruled out."
                    ),
                }
            return {"ok": False, "error": f"unsupported tool {tool}"}
        except SandboxError as exc:
            metrics.backtest_failures += 1
            if "world model static audit" in str(exc):
                metrics.wm_complexity_rejections += 1
            self.workspace.certified = False
            return {"ok": False, "error": f"sandbox: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _handle_schema_cycle(
        self,
        args: dict[str, Any],
        current: Observation,
        history: list[Transition],
        metrics: RunMetrics,
        journal: AppendOnlyJournal,
    ) -> tuple[CommitRequest | None, JsonDict]:
        """Codex 复合回合：应用 workspace_edits → 更新假说 → 自动 backtest/BFS → 选通道 commit。"""
        strategy = str(args.get("strategy", "auto")).strip().lower()
        if strategy not in {"auto", "bfs", "navigation", "exploration"}:
            return None, {
                "ok": False,
                "error": "strategy must be auto|bfs|navigation|exploration",
            }
        edit_results: JsonDict = {}
        raw_edits = args.get("workspace_edits")
        if isinstance(raw_edits, dict):
            source = raw_edits.get("source")
            patch = raw_edits.get("patch")
            if source is not None and patch is not None:
                return None, {
                    "ok": False,
                    "error": "workspace_edits accepts source or patch, not both",
                }
            if source is not None:
                result = self._dispatch_tool(
                    "write_code",
                    {"source": source},
                    current,
                    history,
                    metrics,
                    journal,
                )
                edit_results["world_model"] = result
                if not result.get("ok"):
                    return None, {
                        "ok": False,
                        "error": "schema_cycle workspace source edit failed",
                        "workspace_edits": edit_results,
                    }
            elif isinstance(patch, dict):
                result = self._dispatch_tool(
                    "apply_patch",
                    {"old": patch.get("old", ""), "new": patch.get("new", "")},
                    current,
                    history,
                    metrics,
                    journal,
                )
                edit_results["world_model"] = result
                if not result.get("ok"):
                    return None, {
                        "ok": False,
                        "error": "schema_cycle workspace patch failed",
                        "workspace_edits": edit_results,
                    }
            if raw_edits.get("notes_text") is not None:
                notes_result = self._dispatch_tool(
                    "write_notes",
                    {"text": raw_edits.get("notes_text", "")},
                    current,
                    history,
                    metrics,
                    journal,
                )
                edit_results["notes"] = notes_result
                if not notes_result.get("ok"):
                    return None, {
                        "ok": False,
                        "error": "schema_cycle notes edit failed",
                        "workspace_edits": edit_results,
                    }
        hypothesis_result: JsonDict | None = None
        raw_hypothesis_updates = args.get("hypothesis_updates")
        if isinstance(raw_hypothesis_updates, dict):
            hypothesis_result = self._dispatch_tool(
                "update_hypotheses",
                raw_hypothesis_updates,
                current,
                history,
                metrics,
                journal,
            )
            if not hypothesis_result.get("ok"):
                return None, {
                    "ok": False,
                    "error": "schema_cycle hypothesis update failed",
                    "workspace_edits": edit_results,
                    "hypothesis_updates": hypothesis_result,
                }
        raw_record = args.get("decision_record")
        record = raw_record if isinstance(raw_record, dict) else {}
        hypothesis_ids = record.get("hypotheses", [])
        evidence_seq = record.get("evidence_seq", [])
        decision_record = {
            "hypotheses": [str(value)[:64] for value in hypothesis_ids]
            if isinstance(hypothesis_ids, list)
            else [],
            "evidence_seq": [int(value) for value in evidence_seq if isinstance(value, int)][:20]
            if isinstance(evidence_seq, list)
            else [],
            "expected_observation": str(record.get("expected_observation", ""))[:1000],
            "revision_trigger": str(record.get("revision_trigger", ""))[:1000],
        }
        journal.append(
            "decision_record",
            {
                "env_step": self.env_actions_so_far,
                "strategy": strategy,
                **decision_record,
            },
        )

        backtest_result = self._dispatch_tool(
            "run_backtest", {}, current, history, metrics, journal
        )
        bfs_result: JsonDict | None = None
        if strategy in {"auto", "bfs"} and self.workspace.certified_exact:
            bfs_result = self._dispatch_tool("run_bfs", {}, current, history, metrics, journal)
            if bfs_result.get("found"):
                actions = [
                    dict(step.get("action", {}))
                    for step in bfs_result.get("steps", [])
                    if isinstance(step, dict) and isinstance(step.get("action"), dict)
                ]
                commit, result = self._handle_commit(
                    {
                        "kind": "planned",
                        "plan_id": bfs_result.get("plan_id"),
                        "actions": actions,
                        "rationale": str(args.get("rationale", "")),
                        "evidence_seq": decision_record["evidence_seq"],
                    },
                    current,
                    history,
                )
                if commit is not None:
                    return commit, {
                        "ok": True,
                        "selected_kind": "planned",
                        "plan_id": bfs_result.get("plan_id"),
                        "backtest": backtest_result,
                        "bfs": bfs_result,
                        "workspace_edits": edit_results,
                        "hypothesis_updates": hypothesis_result,
                        "decision_record": decision_record,
                    }

        raw_navigation = args.get("navigation_actions", [])
        if (
            strategy in {"auto", "navigation"}
            and self.workspace.certified
            and isinstance(raw_navigation, list)
            and raw_navigation
        ):
            commit, navigation_result = self._handle_commit(
                {
                    "kind": "navigation",
                    "actions": raw_navigation,
                    "rationale": str(args.get("rationale", "")),
                    "evidence_seq": decision_record["evidence_seq"],
                },
                current,
                history,
            )
            if commit is not None:
                return commit, {
                    "ok": True,
                    "selected_kind": "navigation",
                    "backtest": backtest_result,
                    "bfs": bfs_result,
                    "navigation": navigation_result,
                    "workspace_edits": edit_results,
                    "hypothesis_updates": hypothesis_result,
                    "decision_record": decision_record,
                }

        raw_exploration = args.get("exploration_action")
        if isinstance(raw_exploration, (dict, int)):
            commit, exploration_result = self._handle_commit(
                {
                    "kind": "exploration",
                    "experiment_id": args.get("experiment_id"),
                    "actions": [raw_exploration],
                    "rationale": str(args.get("rationale", "")),
                    "evidence_seq": decision_record["evidence_seq"],
                },
                current,
                history,
            )
            if commit is not None:
                return commit, {
                    "ok": True,
                    "selected_kind": "exploration",
                    "backtest": backtest_result,
                    "bfs": bfs_result,
                    "exploration": exploration_result,
                    "workspace_edits": edit_results,
                    "hypothesis_updates": hypothesis_result,
                    "decision_record": decision_record,
                }

        return None, {
            "ok": False,
            "error": "schema_cycle produced no valid planned/navigation/exploration commit",
            "backtest": backtest_result,
            "bfs": bfs_result,
            "workspace_edits": edit_results,
            "hypothesis_updates": hypothesis_result,
            "decision_record": decision_record,
            "instruction": (
                "Revise world_model.py from the pointed backtest/BFS result, or "
                "supply one legal exploration_action."
            ),
        }

    def _handle_commit(
        self,
        args: dict[str, Any],
        current: Observation,
        history: list[Transition],
    ) -> tuple[CommitRequest | None, JsonDict]:
        """校验 commit 门禁：exploration=1 步；navigation 需 certified；planned 需 exact+plan_id。"""
        del history  # 保留签名与其它工具一致；动作合法性只对照 current
        raw_actions = args.get("actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            return None, {"ok": False, "error": "actions must be a non-empty list"}
        kind = str(args.get("kind", "planned"))
        if kind not in {"planned", "navigation", "exploration"}:
            return None, {
                "ok": False,
                "error": "kind must be planned, navigation, or exploration",
            }
        if kind in {"planned", "navigation"} and self.workspace.mismatch_blocks_planning:
            return None, {
                "ok": False,
                "error": (
                    f"{kind} commit blocked: revise world_model for last_mismatch, "
                    "then run_backtest until certified"
                ),
            }
        if kind in {"planned", "navigation"} and not self.workspace.certified:
            return None, {
                "ok": False,
                "error": (
                    f"{kind} commit requires certified backtest (checked>0); "
                    "use one-step exploration"
                ),
            }
        if kind == "exploration" and len(raw_actions) != 1:
            return None, {
                "ok": False,
                "error": (
                    "exploration commit allows exactly one action; use kind=navigation "
                    "for a certified multi-action subgoal route"
                ),
            }
        if kind == "navigation" and not 2 <= len(raw_actions) <= self.max_plan_steps:
            return None, {
                "ok": False,
                "error": (
                    f"navigation commit requires 2..{self.max_plan_steps} actions; "
                    "use exploration for one action"
                ),
            }
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
        raw_plan_id = args.get("plan_id")
        raw_experiment_id = args.get("experiment_id")
        plan_id = str(raw_plan_id).strip() or None if raw_plan_id is not None else None
        experiment_id = (
            str(raw_experiment_id).strip() or None if raw_experiment_id is not None else None
        )
        if kind == "navigation" and experiment_id is not None:
            return None, {
                "ok": False,
                "error": "navigation cannot be bound to a one-step experiment_id",
            }
        action_payloads = [{"id": action.id, "data": action.data} for action in actions]
        if kind == "planned":
            if not self.workspace.certified_exact:
                return None, {
                    "ok": False,
                    "error": "planned commit requires exact full-Timeline certification",
                }
            pending = self._pending_plan
            if pending is None or plan_id != pending.get("plan_id"):
                return None, {
                    "ok": False,
                    "error": "planned commit requires the current run_bfs plan_id",
                }
            if pending.get("wm_version") != self.workspace.version:
                return None, {
                    "ok": False,
                    "error": "BFS plan invalidated by world-model revision",
                }
            if pending.get("current_fingerprint") != current.fingerprint:
                return None, {
                    "ok": False,
                    "error": "BFS plan invalidated by current-state change",
                }
            if canonical_json(action_payloads) != canonical_json(pending.get("actions")):
                return None, {
                    "ok": False,
                    "error": "planned actions must exactly match the BFS plan",
                }
        if kind == "exploration" and self._pending_experiment is not None:
            pending_experiment = self._pending_experiment
            if experiment_id != pending_experiment.get("experiment_id"):
                return None, {
                    "ok": False,
                    "error": (
                        "an experiment is pending; exploration commit must include "
                        "its experiment_id"
                    ),
                }
            if canonical_json(action_payloads[0]) != canonical_json(
                pending_experiment.get("action")
            ):
                return None, {
                    "ok": False,
                    "error": "exploration action must match the registered experiment",
                }
        if kind == "exploration" and self._pending_experiment is None and experiment_id is not None:
            return None, {
                "ok": False,
                "error": "unknown or stale experiment_id",
            }
        evidence_raw = args.get("evidence_seq", [])
        if not isinstance(evidence_raw, list):
            evidence_raw = []
        evidence_seq = tuple(int(value) for value in evidence_raw if isinstance(value, int))[:20]
        rationale = str(args.get("rationale", "")).strip()[:2000]
        return (
            CommitRequest(
                actions=actions,
                kind=kind,
                reason=str(args.get("reason", "")),
                plan_id=plan_id,
                experiment_id=experiment_id,
                rationale=rationale,
                evidence_seq=evidence_seq,
            ),
            {
                "ok": True,
                "accepted": len(actions),
                "kind": kind,
                "plan_id": plan_id,
                "experiment_id": experiment_id,
            },
        )


def ensure_model_predictions(
    model: ProgramWorldModel,
    before: Observation,
    action: Action,
    after: Observation,
) -> bool:
    """执行后核对：模型对 (before, action) 的预测是否与真实 after 一致。"""
    try:
        runtime = model.start_runtime(before)
        prediction = model.predict_runtime(runtime, action)
    except SandboxError:
        return False
    return prediction_matches(prediction, after)
