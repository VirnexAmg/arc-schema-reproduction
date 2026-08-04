"""Build auditable, presentation-sized data from the three immutable ls20 runs.

The script only reads experiment-runs/ and writes derived files beside the site.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SITE = Path(__file__).resolve().parents[1]

RUNS = {
    "phase1": {
        "id": "20260722T100318.351779Z",
        "label": "Phase 1 · 主案例",
        "short": "80 步预算",
    },
    "phase2": {
        "id": "20260722T110925.665615Z",
        "label": "Phase 2 · 长迭代",
        "short": "220 步预算",
    },
    "deepseek": {
        "id": "20260724T094149.364803Z",
        "label": "DeepSeek D2 · 弱对比",
        "short": "双方 0 关",
    },
}

KEYWORDS = {
    "cross": {
        "label": "十字 / cross",
        "pattern": r"十字|\bcross(?:es|ed|ing)?\b",
    },
    "rotate": {
        "label": "旋转 / rotate",
        "pattern": r"旋转|旋轉|\brotation\b|\brotat(?:e|es|ed|ing)\b",
    },
    "clockwise_90": {
        "label": "顺时针 / 90°",
        "pattern": r"顺时针|順時針|clockwise|90\s*(?:°|degrees?|deg\b)",
    },
    "three_by_three": {
        "label": "3×3",
        "pattern": r"3\s*[x×]\s*3|\b3-by-3\b",
    },
    "match_target": {
        "label": "对齐目标 / match target",
        "pattern": (
            r"对齐|匹配目标|与目标.{0,12}(?:一致|相同)|"
            r"\bmatch(?:es|ed|ing)?\b.{0,24}\b(?:target|goal)\b|"
            r"\b(?:target|goal)\b.{0,24}\bmatch(?:es|ed|ing)?\b"
        ),
    },
    "coordinate": {
        "label": "坐标 / coordinate",
        "pattern": r"坐标|\bcoordinate\b|\(\s*\d+\s*,\s*\d+\s*\)",
    },
    "key": {
        "label": "钥匙 / key",
        "pattern": r"钥匙|\bkey(?:ed|s)?\b",
    },
    "chamber": {
        "label": "房间 / chamber / shrine",
        "pattern": r"房间|\bchamber\b|\bshrine\b",
    },
    "levels": {
        "label": "levels_completed",
        "pattern": r"\blevels_completed\b",
    },
}


def compact(value: Any, limit: int = 950) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def extract_comments(source: str) -> list[str]:
    comments: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            text = stripped.lstrip("#").strip()
            if text and text not in comments:
                comments.append(text)
    return comments


def decode_frame(frame_rle: Any) -> list[list[int]]:
    if not isinstance(frame_rle, list):
        return []
    frame: list[list[int]] = []
    for spec in frame_rle:
        row: list[int] = []
        for part in str(spec).split(","):
            color, count = part.split(":")
            row.extend([int(color)] * int(count))
        frame.append(row)
    return frame


def player_position(state: dict[str, Any]) -> list[int] | None:
    frame = decode_frame(state.get("frame_rle"))
    if not frame or not frame[0]:
        return None
    height = len(frame)
    width = len(frame[0])
    for y in range(max(0, height - 4)):
        for x in range(max(0, width - 4)):
            matched = True
            for dy in range(5):
                expected = 12 if dy < 2 else 9
                if any(frame[y + dy][x + dx] != expected for dx in range(5)):
                    matched = False
                    break
            if matched:
                return [x, y]
    return None


def scan_text(text: str, *, origin: str, line_no: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = text.splitlines() or [text]
    for key, spec in KEYWORDS.items():
        regex = re.compile(spec["pattern"], re.IGNORECASE)
        hits = []
        for local_line, line in enumerate(lines, start=1):
            if regex.search(line):
                hits.append(
                    {
                        "origin": origin,
                        "line": line_no if line_no is not None else local_line,
                        "local_line": local_line if line_no is not None else None,
                        "text": compact(line.strip(), 360),
                    }
                )
        result[key] = {"label": spec["label"], "count": len(hits), "hits": hits[:12]}
    return result


def merge_scans(scans: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, spec in KEYWORDS.items():
        hits = []
        count = 0
        for scan in scans:
            count += scan[key]["count"]
            hits.extend(scan[key]["hits"])
        merged[key] = {
            "label": spec["label"],
            "count": count,
            "hits": hits[:16],
        }
    return merged


def backtest_detail(result: Any) -> str:
    if not isinstance(result, dict):
        return compact(result, 600)
    payload = result.get("result")
    if isinstance(payload, dict):
        for key in ("message", "error", "reason"):
            if payload.get(key):
                return compact(payload[key], 600)
        failures = payload.get("failures")
        if isinstance(failures, list) and failures:
            return compact(failures[0], 600)
    for key in ("message", "error", "reason"):
        if result.get(key):
            return compact(result[key], 600)
    return compact(payload, 600) if payload else ""


def parse_run(key: str, spec: dict[str, str]) -> dict[str, Any]:
    run_dir = ROOT / "experiment-runs" / spec["id"]
    log_path = run_dir / "harness-run-0.jsonl"
    exp_path = run_dir / "experiment.json"
    wm_path = run_dir / "workspace-harness-0" / "world_model.py"
    notes_path = run_dir / "workspace-harness-0" / "notes.md"

    with exp_path.open("r", encoding="utf-8") as handle:
        experiment = json.load(handle)
    with log_path.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    harness_result = next(
        result for result in experiment["results"] if result["agent"] == "harness"
    )
    baseline_result = next(
        result for result in experiment["results"] if result["agent"] == "baseline"
    )

    event_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    transitions: list[dict[str, Any]] = []
    level_changes: list[dict[str, Any]] = []
    edits: list[dict[str, Any]] = []
    backtests: list[dict[str, Any]] = []
    tool_sequence: list[dict[str, Any]] = []
    code_scans: list[dict[str, Any]] = []
    model_text_scans: list[dict[str, Any]] = []
    env_step = 0
    edit_index = 0
    backtest_index = 0
    current_version: int | None = None

    for line_no, row in enumerate(rows, start=1):
        event = row.get("event", "")
        payload = row.get("payload") or {}
        event_counts[event] += 1

        if event == "transition":
            env_step += 1
            before = payload.get("before") or {}
            after = payload.get("after") or {}
            action = payload.get("action") or {}
            transition = {
                "step": env_step,
                "line": line_no,
                "sequence": row.get("sequence"),
                "time": row.get("timestamp"),
                "action": action.get("id"),
                "kind": payload.get("kind"),
                "levels_before": before.get("levels_completed"),
                "levels_after": after.get("levels_completed"),
                "state_before": before.get("state"),
                "state_after": after.get("state"),
                "player_before": player_position(before),
                "player_after": player_position(after),
                "bbox": (payload.get("delta") or {}).get("bbox"),
            }
            transitions.append(transition)
            if transition["levels_before"] != transition["levels_after"]:
                level_changes.append(transition)
            continue

        if event != "deliberation_tool":
            continue

        tool = payload.get("tool", "")
        args = payload.get("args") or {}
        result = payload.get("result")
        tool_counts[tool] += 1
        tool_sequence.append(
            {
                "line": line_no,
                "sequence": row.get("sequence"),
                "time": row.get("timestamp"),
                "step": env_step,
                "tool": tool,
                "args": compact(args, 1000),
                "result": compact(result, 700),
            }
        )

        if tool in {"write_code", "apply_patch"}:
            edit_index += 1
            if isinstance(result, dict) and result.get("version") is not None:
                current_version = result["version"]
            new_text = args.get("source", "") if tool == "write_code" else args.get("new", "")
            old_text = "" if tool == "write_code" else args.get("old", "")
            comments = extract_comments(new_text)
            edit = {
                "index": edit_index,
                "line": line_no,
                "sequence": row.get("sequence"),
                "time": row.get("timestamp"),
                "step": env_step,
                "tool": tool,
                "version": current_version,
                "comments": comments,
                "old": compact(old_text, 1200),
                "new": compact(new_text, 2000),
                "old_length": len(old_text),
                "new_length": len(new_text),
            }
            edits.append(edit)
            code_scans.append(
                scan_text(
                    new_text,
                    origin=f"jsonl · 第 {line_no} 行 · {tool}",
                    line_no=line_no,
                )
            )

        elif tool == "write_notes":
            note_text = args.get("content") or args.get("text") or compact(args, 4000)
            model_text_scans.append(
                scan_text(
                    note_text,
                    origin=f"jsonl · 第 {line_no} 行 · write_notes",
                    line_no=line_no,
                )
            )

        elif tool == "run_backtest":
            backtest_index += 1
            certified = bool(result.get("certified")) if isinstance(result, dict) else False
            ok = bool(result.get("ok")) if isinstance(result, dict) else False
            backtests.append(
                {
                    "index": backtest_index,
                    "line": line_no,
                    "sequence": row.get("sequence"),
                    "time": row.get("timestamp"),
                    "step": env_step,
                    "version": current_version,
                    "passed": certified,
                    "ok": ok,
                    "detail": backtest_detail(result),
                }
            )

    world_model = wm_path.read_text(encoding="utf-8")
    notes = notes_path.read_text(encoding="utf-8")
    notes_template = notes.strip() == (
        "# Working notes\nInfer objects and mechanisms from transitions only."
    )

    model_code_scan = merge_scans(code_scans) if code_scans else merge_scans([])
    model_notes_scan = merge_scans(model_text_scans) if model_text_scans else merge_scans([])

    return {
        "key": key,
        "label": spec["label"],
        "short": spec["short"],
        "run_id": spec["id"],
        "model": experiment["config"]["model"]["model"],
        "config": {
            "max_environment_actions": experiment["config"]["max_environment_actions"],
            "vision_enabled": experiment["config"]["model"]["vision_enabled"],
            "render_mode": experiment["config"].get("render_mode"),
        },
        "harness": {
            "levels_completed": harness_result["levels_completed"],
            "status": harness_result["status"],
            "score": harness_result["score"],
            "environment_actions": harness_result["environment_actions"],
            "exploration_actions": harness_result["exploration_actions"],
            "planned_actions": harness_result["planned_actions"],
            "model_calls": harness_result["model_calls"],
            "backtest_failures": harness_result["backtest_failures"],
            "prediction_mismatches": harness_result["prediction_mismatches"],
            "estimated_cost_usd": harness_result["usage"]["estimated_cost_usd"],
            "wall_clock_seconds": harness_result["wall_clock_seconds"],
        },
        "baseline": {
            "levels_completed": baseline_result["levels_completed"],
            "status": baseline_result["status"],
            "environment_actions": baseline_result["environment_actions"],
            "estimated_cost_usd": baseline_result["usage"]["estimated_cost_usd"],
            "wall_clock_seconds": baseline_result["wall_clock_seconds"],
        },
        "event_counts": dict(sorted(event_counts.items())),
        "tool_counts": dict(sorted(tool_counts.items())),
        "transitions": transitions,
        "level_changes": level_changes,
        "edits": edits,
        "backtests": backtests,
        "backtest_summary": {
            "total": len(backtests),
            "passed": sum(1 for item in backtests if item["passed"]),
            "failed": sum(1 for item in backtests if not item["passed"]),
        },
        "tool_sequence": tool_sequence,
        "notes": {
            "text": notes,
            "template_only": notes_template,
            "write_calls": tool_counts.get("write_notes", 0),
        },
        "keyword_scan": {
            "final_world_model": scan_text(
                world_model,
                origin=f"{spec['id']}/workspace-harness-0/world_model.py",
            ),
            "final_notes": scan_text(
                notes,
                origin=f"{spec['id']}/workspace-harness-0/notes.md",
            ),
            "all_code_edits": model_code_scan,
            "write_notes_events": model_notes_scan,
        },
        "world_model_excerpt": {
            "comments": extract_comments(world_model),
            "line_count": len(world_model.splitlines()),
        },
        "sources": {
            "jsonl": f"experiment-runs/{spec['id']}/harness-run-0.jsonl",
            "world_model": (f"experiment-runs/{spec['id']}/workspace-harness-0/world_model.py"),
            "notes": f"experiment-runs/{spec['id']}/workspace-harness-0/notes.md",
            "experiment": f"experiment-runs/{spec['id']}/experiment.json",
        },
    }


def main() -> None:
    cases = {key: parse_run(key, spec) for key, spec in RUNS.items()}
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": (
            "由 scripts/extract_case_data.py 从三份只读 experiment-runs 原始记录生成；"
            "页面结论与叙事分组在前端显式标注。"
        ),
        "cases": cases,
    }
    target = SITE / "case-data.json"
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    js_target = SITE / "case-data.js"
    js_target.write_text(
        "window.LS20_CASE_DATA = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {target.relative_to(ROOT)}")
    for key, case in cases.items():
        summary = case["backtest_summary"]
        level = case["level_changes"]
        level_text = (
            ", ".join(
                f"step {item['step']}: {item['levels_before']}→{item['levels_after']}"
                for item in level
            )
            or "none"
        )
        print(
            f"{key}: {len(case['edits'])} edits, "
            f"{summary['passed']}/{summary['total']} certified backtests, "
            f"level changes {level_text}"
        )


if __name__ == "__main__":
    main()
