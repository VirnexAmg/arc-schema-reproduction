from __future__ import annotations

"""
单次运行的持久 Workspace：落地 world_model.py + notes.md，并跟踪认证状态。

本模块是 agent 改代码与 ProgramWorldModel 执行之间的薄适配层：
1. 初始化时确保目录与默认 stub/笔记存在；
2. write_code 整文件写入并重载模型；apply_patch 要求唯一子串替换后走同一写路径；
3. 任何代码变更都会 version+1、清除 certified/last_backtest，强制重新回测；
4. model() 缓存已加载的 ProgramWorldModel；record_mismatch 记录失败现场并取消认证；
5. notes / world_model / hypotheses 修订写入旁路历史，便于事后抽查演变。

阅读导引：
- world_model.py / notes.md / hypotheses.json：磁盘上的外显记忆
- certified / certified_exact：认证位（exact 才能 BFS/planned；approximate 仅 navigation）
- mismatch_blocks_planning + BFS no-plan cooldown：失败后的门禁与搜索冷却
- hypothesis_context()：给模型的裁剪视图（去掉 lineage 与大体积 delta）
- update_hypotheses()：假说状态 active|supported|rejected|uncertain

回测通过后的 certified=True 由上层（如 deliberation）设置；本文件只保证「改码即失效」。
"""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from arc_schema.program_world_model import (
    DEFAULT_WORLD_MODEL_STUB,
    ProgramBacktestResult,
    ProgramWorldModel,
    world_model_complexity,
    world_model_complexity_warnings,
)


HYPOTHESIS_ID_PATTERN = re.compile(r"^H_[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
HYPOTHESIS_STATUSES = frozenset({"active", "supported", "rejected", "uncertain"})
HYPOTHESIS_STATUS_ALIASES = {"confirmed": "supported"}
SOFT_TOTAL_HYPOTHESES = 24
SOFT_ACTIVE_HYPOTHESES = 8
HARD_TOTAL_HYPOTHESES = 128
HARD_ACTIVE_HYPOTHESES = 48
HARD_UNREVIEWED_EXPERIMENTS = 32
PROMPT_MAX_HYPOTHESES = 12
PROMPT_MAX_EXPERIMENTS = 6
PROMPT_LEDGER_MAX_CHARS = 12000
BFS_NO_PLAN_COOLDOWN_ACTIONS = 8


def _clip_prompt_text(value: object, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _compact_hypothesis(hypothesis_id: str, item: dict) -> dict:
    history = item.get("statement_history", [])
    return {
        "id": hypothesis_id,
        "status": str(item.get("status", "uncertain")),
        "statement": _clip_prompt_text(item.get("statement"), 600),
        "recent_evidence_seq": [
            int(value) for value in item.get("evidence_seq", [])[-8:] if isinstance(value, int)
        ],
        "last_reason": _clip_prompt_text(item.get("last_reason"), 240),
        "prior_statement_count": len(history) if isinstance(history, list) else 0,
    }


def _compact_experiment(experiment_id: str, item: dict) -> dict:
    hypotheses = []
    for hypothesis in item.get("hypotheses", [])[:4]:
        if not isinstance(hypothesis, dict):
            continue
        hypotheses.append(
            {
                "id": _clip_prompt_text(hypothesis.get("id"), 64),
                "prediction": _clip_prompt_text(hypothesis.get("prediction"), 240),
            }
        )
    outcome = item.get("outcome")
    compact_outcome = None
    if isinstance(outcome, dict):
        delta = outcome.get("delta")
        compact_delta = {}
        if isinstance(delta, dict):
            if delta.get("bbox") is not None:
                compact_delta["bbox"] = delta.get("bbox")
            metadata = delta.get("metadata")
            if isinstance(metadata, dict) and metadata:
                compact_delta["metadata"] = metadata
            rows = delta.get("rows")
            if isinstance(rows, list):
                compact_delta["changed_row_count"] = len(rows)
        compact_outcome = {
            "action": outcome.get("action"),
            "levels_before": outcome.get("levels_before"),
            "levels_after": outcome.get("levels_after"),
            "state_after": outcome.get("state_after"),
            "delta_summary": compact_delta,
        }
    return {
        "experiment_id": experiment_id,
        "status": str(item.get("status", "unknown")),
        "action": item.get("action"),
        "hypotheses": hypotheses,
        "rationale": _clip_prompt_text(item.get("rationale"), 240),
        "outcome": compact_outcome,
        "resolution_reason": _clip_prompt_text(item.get("resolution_reason"), 240),
    }


@dataclass
class Workspace:
    """一次运行的持久 Schema 记忆：代码、笔记、假说账本与认证门禁状态。"""

    root: Path
    version: int = 0  # world_model.py 版本；改码 +1
    notes_version: int = 0
    hypothesis_version: int = 0
    last_backtest: ProgramBacktestResult | None = None
    certified: bool = False  # 全 Timeline 回测通过且 checked>0
    certified_exact: bool = False  # 无 approximate 匹配；BFS/planned 必需
    last_mismatch: dict | None = None
    # 预测 mismatch（或 life_reset）后，planned/navigation 被挡，直到改码并重新认证。
    mismatch_blocks_planning: bool = False
    planning_block_reason: str | None = None
    required_revision_version: int = 0
    bfs_no_plan_wm_version: int | None = None  # BFS 无解冷却：绑定 WM/关卡/步数
    bfs_no_plan_level: int | None = None
    bfs_no_plan_env_step: int | None = None
    _model: ProgramWorldModel | None = field(default=None, repr=False)
    _accepted_code: str = field(default="", repr=False)
    _accepted_notes: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.wm_versions_dir.mkdir(parents=True, exist_ok=True)
        self.notes_history_dir.mkdir(parents=True, exist_ok=True)
        self.hypothesis_versions_dir.mkdir(parents=True, exist_ok=True)
        self.vision_frames_dir.mkdir(parents=True, exist_ok=True)
        if not self.world_model_path.exists():
            self.write_code(DEFAULT_WORLD_MODEL_STUB)
        if not self.notes_path.exists():
            self.notes_path.write_text(
                "# Working notes\n"
                "Infer objects and mechanisms from transitions only.\n"
                "\n"
                "## Hypotheses\n"
                "- (write competing mechanism hypotheses here)\n"
                "\n"
                "## Experiments\n"
                "- (what you tried and what it ruled out)\n",
                encoding="utf-8",
            )
        if not self.hypothesis_ledger_path.exists():
            self.hypothesis_ledger_path.write_text(
                json.dumps(
                    {"version": 0, "hypotheses": {}, "experiments": {}},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        ledger = self.read_hypothesis_ledger()
        self.hypothesis_version = int(ledger.get("version", 0))
        self._accepted_code = self.read_code()
        self._accepted_notes = self.read_notes()

    @property
    def world_model_path(self) -> Path:
        return self.root / "world_model.py"

    @property
    def notes_path(self) -> Path:
        return self.root / "notes.md"

    @property
    def wm_versions_dir(self) -> Path:
        return self.root / "wm_versions"

    @property
    def notes_history_dir(self) -> Path:
        return self.root / "notes_history"

    @property
    def hypothesis_ledger_path(self) -> Path:
        return self.root / "hypotheses.json"

    @property
    def hypothesis_versions_dir(self) -> Path:
        return self.root / "hypothesis_versions"

    @property
    def vision_frames_dir(self) -> Path:
        return self.root / "vision_frames"

    def read_code(self) -> str:
        return self.world_model_path.read_text(encoding="utf-8")

    def read_notes(self) -> str:
        return self.notes_path.read_text(encoding="utf-8")

    def read_hypothesis_ledger(self) -> dict:
        value = json.loads(self.hypothesis_ledger_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("hypotheses.json must contain an object")
        value.setdefault("version", 0)
        value.setdefault("hypotheses", {})
        value.setdefault("experiments", {})
        return value

    def _write_hypothesis_ledger(self, ledger: dict) -> int:
        self.hypothesis_version = (
            max(
                self.hypothesis_version,
                int(ledger.get("version", 0)),
            )
            + 1
        )
        ledger["version"] = self.hypothesis_version
        text = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
        self.hypothesis_ledger_path.write_text(text, encoding="utf-8")
        snapshot = self.hypothesis_versions_dir / f"v{self.hypothesis_version:04d}.json"
        snapshot.write_text(text, encoding="utf-8")
        return self.hypothesis_version

    def active_hypothesis_ids(self) -> set[str]:
        ledger = self.read_hypothesis_ledger()
        return {
            str(hypothesis_id)
            for hypothesis_id, item in ledger["hypotheses"].items()
            if item.get("status") in {"active", "supported", "uncertain"}
        }

    def hypothesis_context(
        self,
        *,
        max_hypotheses: int = PROMPT_MAX_HYPOTHESES,
        max_experiments: int = PROMPT_MAX_EXPERIMENTS,
        max_chars: int = PROMPT_LEDGER_MAX_CHARS,
    ) -> dict:
        """给模型的有界假说视图；完整 lineage 与大体积 delta 只留磁盘。"""
        ledger = self.read_hypothesis_ledger()
        items = list(ledger["hypotheses"].items())
        recent_experiments = list(ledger["experiments"].values())[-max_experiments:]
        decision_relevant_ids = {
            str(hypothesis.get("id", ""))
            for experiment in recent_experiments
            if isinstance(experiment, dict) and experiment.get("status") in {"proposed", "observed"}
            for hypothesis in experiment.get("hypotheses", [])
            if isinstance(hypothesis, dict)
        }
        status_rank = {"supported": 0, "active": 1, "uncertain": 2, "rejected": 3}
        items.sort(
            key=lambda pair: (
                status_rank.get(str(pair[1].get("status", "active")), 2),
                pair[0] not in decision_relevant_ids,
                -int(pair[1].get("last_updated_version", 0) or 0),
                -max(
                    [
                        int(value)
                        for value in pair[1].get("evidence_seq", [])
                        if isinstance(value, int)
                    ],
                    default=-1,
                ),
                pair[0],
            )
        )
        selected_hypotheses = items[:max_hypotheses]
        selected_experiments = list(ledger["experiments"].items())[-max_experiments:]
        payload = {
            "version": ledger["version"],
            "hypotheses": {
                hypothesis_id: _compact_hypothesis(hypothesis_id, item)
                for hypothesis_id, item in selected_hypotheses
            },
            "experiments": {
                experiment_id: _compact_experiment(experiment_id, item)
                for experiment_id, item in selected_experiments
            },
            "omitted_hypotheses": max(0, len(items) - len(selected_hypotheses)),
            "omitted_experiments": max(
                0,
                len(ledger["experiments"]) - len(selected_experiments),
            ),
            "context_truncated": False,
            "context_chars": 0,
        }
        while len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > max(
            0, max_chars - 64
        ):
            if len(payload["hypotheses"]) > 8:
                last = next(reversed(payload["hypotheses"]))
                del payload["hypotheses"][last]
                payload["omitted_hypotheses"] += 1
            elif len(payload["experiments"]) > 2:
                oldest = next(iter(payload["experiments"]))
                del payload["experiments"][oldest]
                payload["omitted_experiments"] += 1
            elif len(payload["hypotheses"]) > 4:
                last = next(reversed(payload["hypotheses"]))
                del payload["hypotheses"][last]
                payload["omitted_hypotheses"] += 1
            elif payload["experiments"]:
                oldest = next(iter(payload["experiments"]))
                del payload["experiments"][oldest]
                payload["omitted_experiments"] += 1
            else:
                for hypothesis in payload["hypotheses"].values():
                    hypothesis["statement"] = _clip_prompt_text(hypothesis.get("statement"), 200)
                    hypothesis["last_reason"] = _clip_prompt_text(hypothesis.get("last_reason"), 80)
                break
            payload["context_truncated"] = True
        for _ in range(3):
            payload["context_chars"] = len(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            )
        return payload

    def bfs_advisory(self, *, level: int, env_step: int) -> dict:
        same_failed_search = (
            self.bfs_no_plan_wm_version == self.version
            and self.bfs_no_plan_level == level
            and self.bfs_no_plan_env_step is not None
        )
        remaining = 0
        if same_failed_search:
            assert self.bfs_no_plan_env_step is not None
            remaining = max(
                0,
                self.bfs_no_plan_env_step + BFS_NO_PLAN_COOLDOWN_ACTIONS - env_step,
            )
        return {
            "available": not same_failed_search or remaining == 0,
            "cooldown_actions_remaining": remaining,
            "last_no_plan_wm_version": self.bfs_no_plan_wm_version,
            "last_no_plan_level": self.bfs_no_plan_level,
            "last_no_plan_env_step": self.bfs_no_plan_env_step,
        }

    def record_bfs_no_plan(self, *, level: int, env_step: int) -> None:
        self.bfs_no_plan_wm_version = self.version
        self.bfs_no_plan_level = level
        self.bfs_no_plan_env_step = env_step

    def clear_bfs_no_plan(self) -> None:
        self.bfs_no_plan_wm_version = None
        self.bfs_no_plan_level = None
        self.bfs_no_plan_env_step = None

    def update_hypotheses(
        self,
        items: list[dict],
        *,
        evidence_seq: list[int],
        reason: str,
        experiment_id: str | None = None,
    ) -> dict:
        """Create or revise useful hypotheses while retaining their full lineage."""
        if not items:
            raise ValueError("at least one hypothesis update is required")
        ledger = self.read_hypothesis_ledger()
        candidate = json.loads(json.dumps(ledger))
        hypotheses = candidate["hypotheses"]
        updated_ids: list[str] = []
        status_normalizations: list[dict[str, str]] = []
        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError("each hypothesis update must be an object")
            hypothesis_id = str(raw.get("id", "")).strip()
            if not HYPOTHESIS_ID_PATTERN.fullmatch(hypothesis_id):
                raise ValueError(
                    "hypothesis id must match H_<stable-name> using letters/digits/_/-"
                )
            statement = str(raw.get("statement", "")).strip()
            supplied_status = str(raw.get("status", "active")).strip().lower()
            status = HYPOTHESIS_STATUS_ALIASES.get(supplied_status, supplied_status)
            if status != supplied_status:
                status_normalizations.append(
                    {
                        "hypothesis_id": hypothesis_id,
                        "from": supplied_status,
                        "to": status,
                    }
                )
            if status not in HYPOTHESIS_STATUSES:
                raise ValueError("hypothesis status must be active|supported|rejected|uncertain")
            existing = hypotheses.get(hypothesis_id)
            if existing is None:
                if not statement:
                    raise ValueError(f"new hypothesis {hypothesis_id} requires statement")
                if len(hypotheses) >= HARD_TOTAL_HYPOTHESES:
                    raise ValueError(
                        f"hypothesis ledger hard safety limit reached ({HARD_TOTAL_HYPOTHESES})"
                    )
                hypotheses[hypothesis_id] = {
                    "id": hypothesis_id,
                    "statement": statement[:2000],
                    "status": status,
                    "evidence_seq": sorted(set(evidence_seq)),
                    "last_reason": reason[:1000],
                    "last_updated_version": int(candidate.get("version", 0)) + 1,
                }
            else:
                if statement and statement != str(existing.get("statement", "")):
                    history = existing.setdefault("statement_history", [])
                    history.append(
                        {
                            "statement": str(existing.get("statement", "")),
                            "evidence_seq": list(existing.get("evidence_seq", [])),
                            "reason": str(existing.get("last_reason", "")),
                            "revised_at_ledger_version": int(candidate.get("version", 0)) + 1,
                        }
                    )
                    existing["statement_history"] = history[-20:]
                    existing["statement"] = statement[:2000]
                existing["status"] = status
                existing["evidence_seq"] = sorted(
                    {
                        *(
                            int(value)
                            for value in existing.get("evidence_seq", [])
                            if isinstance(value, int)
                        ),
                        *evidence_seq,
                    }
                )[-100:]
                existing["last_reason"] = reason[:1000]
                existing["last_updated_version"] = int(candidate.get("version", 0)) + 1
            updated_ids.append(hypothesis_id)

        active_count = sum(
            item.get("status") in {"active", "supported", "uncertain"}
            for item in hypotheses.values()
        )
        if active_count > HARD_ACTIVE_HYPOTHESES:
            raise ValueError(
                f"too many unresolved hypotheses ({active_count}); hard safety "
                f"limit is {HARD_ACTIVE_HYPOTHESES}"
            )
        warnings: list[str] = []
        if len(hypotheses) > SOFT_TOTAL_HYPOTHESES:
            warnings.append(
                f"{len(hypotheses)} hypotheses exceed soft context target "
                f"{SOFT_TOTAL_HYPOTHESES}; consolidate when convenient"
            )
        if active_count > SOFT_ACTIVE_HYPOTHESES:
            warnings.append(
                f"{active_count} unresolved hypotheses exceed soft target "
                f"{SOFT_ACTIVE_HYPOTHESES}; this does not block action"
            )

        if experiment_id:
            experiment = candidate["experiments"].get(experiment_id)
            if experiment is None:
                raise ValueError(f"unknown experiment_id {experiment_id}")
            if experiment.get("status") != "observed":
                raise ValueError("experiment must have an observed outcome before resolution")
            expected_ids = {str(item["id"]) for item in experiment.get("hypotheses", [])}
            if not expected_ids.intersection(updated_ids):
                raise ValueError(
                    "reviewing an experiment must update at least one compared hypothesis"
                )
            experiment["status"] = "reviewed"
            experiment["resolution_reason"] = reason[:1000]
            experiment["resolution_evidence_seq"] = sorted(set(evidence_seq))

        version = self._write_hypothesis_ledger(candidate)
        return {
            "version": version,
            "updated_ids": updated_ids,
            "active_count": active_count,
            "experiment_id": experiment_id,
            "status_normalizations": status_normalizations,
            "warnings": warnings,
        }

    def register_experiment(self, binding: dict) -> int:
        ledger = self.read_hypothesis_ledger()
        candidate = json.loads(json.dumps(ledger))
        experiments = candidate["experiments"]
        experiment_id = str(binding["experiment_id"])
        if experiment_id in experiments:
            raise ValueError(f"experiment_id already exists: {experiment_id}")
        pending_here = [
            item
            for item in experiments.values()
            if (
                item.get("status") == "proposed"
                and item.get("current_fingerprint") == binding.get("current_fingerprint")
            )
        ]
        if pending_here:
            raise ValueError(
                "commit the already proposed experiment for this state before creating another"
            )
        unreviewed = [
            item for item in experiments.values() if item.get("status") in {"proposed", "observed"}
        ]
        if len(unreviewed) >= HARD_UNREVIEWED_EXPERIMENTS:
            raise ValueError("too many unreviewed experiments; hard audit safety limit reached")
        active_ids = self.active_hypothesis_ids()
        referenced = {str(item["id"]) for item in binding.get("hypotheses", [])}
        if len(referenced) < 2 or not referenced.issubset(active_ids):
            raise ValueError(
                "experiments must compare at least two existing unresolved hypothesis IDs"
            )
        experiments[experiment_id] = {
            **binding,
            "status": "proposed",
        }
        return self._write_hypothesis_ledger(candidate)

    def pending_experiment(self, current_fingerprint: str) -> dict | None:
        ledger = self.read_hypothesis_ledger()
        for item in reversed(list(ledger["experiments"].values())):
            if (
                item.get("status") == "proposed"
                and item.get("current_fingerprint") == current_fingerprint
            ):
                return item
        return None

    def unresolved_observed_experiments(self) -> list[dict]:
        ledger = self.read_hypothesis_ledger()
        return [item for item in ledger["experiments"].values() if item.get("status") == "observed"]

    def record_experiment_outcome(
        self,
        experiment_id: str,
        outcome: dict,
        *,
        evidence_seq: int,
    ) -> int:
        ledger = self.read_hypothesis_ledger()
        candidate = json.loads(json.dumps(ledger))
        experiment = candidate["experiments"].get(experiment_id)
        if experiment is None:
            raise ValueError(f"unknown experiment_id {experiment_id}")
        if experiment.get("status") != "proposed":
            raise ValueError(f"experiment {experiment_id} is not pending")
        experiment["status"] = "observed"
        experiment["outcome"] = outcome
        experiment["outcome_evidence_seq"] = evidence_seq
        return self._write_hypothesis_ledger(candidate)

    def write_notes(self, text: str) -> int:
        """Overwrite notes.md and append a versioned snapshot for audit."""
        self.notes_version += 1
        self.notes_path.write_text(text, encoding="utf-8")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        snapshot = self.notes_history_dir / f"v{self.notes_version:04d}_{stamp}.md"
        snapshot.write_text(text, encoding="utf-8")
        self._accepted_notes = text
        return self.notes_version

    def write_code(self, source: str) -> ProgramWorldModel:
        """整文件覆盖 world_model.py，使认证失效并重新沙箱加载模型。"""
        # Validate before touching the active file so a rejected over-complex patch
        # cannot corrupt the last usable model.
        model = ProgramWorldModel(source)
        self.world_model_path.write_text(source, encoding="utf-8")
        self.version += 1
        self.certified = False
        self.certified_exact = False
        self.last_backtest = None
        self._model = model
        snapshot = self.wm_versions_dir / f"v{self.version:04d}.py"
        snapshot.write_text(source, encoding="utf-8")
        self._accepted_code = source
        return self._model

    def sync_external_changes(self) -> dict:
        """Validate and version edits made directly by a workspace-native agent."""
        result = {
            "code_changed": False,
            "notes_changed": False,
            "wm_version": self.version,
            "notes_version": self.notes_version,
        }
        code = self.read_code()
        if code != self._accepted_code:
            try:
                model = ProgramWorldModel(code)
            except Exception as exc:
                self.world_model_path.write_text(self._accepted_code, encoding="utf-8")
                result["code_error"] = f"{type(exc).__name__}: {exc}"
            else:
                self.version += 1
                self.certified = False
                self.certified_exact = False
                self.last_backtest = None
                self._model = model
                self._accepted_code = code
                snapshot = self.wm_versions_dir / f"v{self.version:04d}.py"
                snapshot.write_text(code, encoding="utf-8")
                result.update(code_changed=True, wm_version=self.version)

        notes = self.read_notes()
        if notes != self._accepted_notes:
            self.notes_version += 1
            self._accepted_notes = notes
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
            snapshot = self.notes_history_dir / f"v{self.notes_version:04d}_{stamp}.md"
            snapshot.write_text(notes, encoding="utf-8")
            result.update(notes_changed=True, notes_version=self.notes_version)
        return result

    def model_complexity(self) -> dict[str, int]:
        return world_model_complexity(self.read_code())

    def model_complexity_warnings(self) -> list[str]:
        return world_model_complexity_warnings(self.read_code())

    def apply_patch(self, old: str, new: str) -> ProgramWorldModel:
        """用唯一子串替换增量编辑 world_model.py（Schema 式文件补丁）。"""
        source = self.read_code()
        if old not in source:
            raise ValueError("patch old text not found in world_model.py")
        count = source.count(old)
        if count != 1:
            raise ValueError(f"patch old text matched {count} times; must be unique")
        return self.write_code(source.replace(old, new, 1))

    def model(self) -> ProgramWorldModel:
        """返回已缓存的 ProgramWorldModel；若无则从磁盘重新加载。"""
        if self._model is None:
            self._model = ProgramWorldModel(self.read_code())
        return self._model

    def record_mismatch(self, payload: dict) -> None:
        """记录反例；必须产生新 WM 版本并重新回测后才能 planned。"""
        self.last_mismatch = payload
        self.certified = False
        self.certified_exact = False
        self.mismatch_blocks_planning = True
        self.planning_block_reason = "prediction_mismatch"
        self.required_revision_version = self.version + 1

    def record_soft_mismatch(self, payload: dict) -> None:
        """Keep an instrumental visual approximation visible without blocking plans."""
        self.last_mismatch = {
            **payload,
            "severity": "soft",
            "planning_blocked": False,
        }

    def record_boundary(self, payload: dict, *, reason: str) -> None:
        """Death/level boundary invalidates old plans but does not force a code edit."""
        self.last_mismatch = payload
        self.certified = False
        self.certified_exact = False
        self.mismatch_blocks_planning = True
        self.planning_block_reason = reason
        self.required_revision_version = self.version

    def clear_mismatch_block(self) -> None:
        """Clear the post-mismatch planning gate after a successful re-certify."""
        self.mismatch_blocks_planning = False
        self.planning_block_reason = None
        self.required_revision_version = self.version
