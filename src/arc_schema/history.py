from __future__ import annotations

"""
哈希链 Journal：只追加的 SHA-256 链式 JSONL，记录整次 run 的可审计事件。

阅读导引：
- AppendOnlyJournal.append(event, payload)：写一条并链接 previous_hash
- verify()：启动时校验链完整；断链或改内容会抛 HistoryIntegrityError
- 产物形如 harness-run-0.jsonl / baseline-run-0.jsonl
注意：有文件系统写权限仍可整文件重写；这是篡改可检测，不是外部 WORM。
"""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from arc_schema.core import canonical_json


GENESIS_HASH = "0" * 64


class HistoryIntegrityError(ValueError):
    """哈希链断裂或记录被篡改。"""


class AppendOnlyJournal:
    """只追加 JSONL + SHA-256 哈希链；使单条静默改写可被检出。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = list(self.read_records(path))
        self._previous_hash = self.verify(records)
        self._sequence = len(records)

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "sequence": self._sequence,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "payload": payload,
            "previous_hash": self._previous_hash,
        }
        record_hash = hashlib.sha256(canonical_json(body).encode()).hexdigest()
        record = {**body, "record_hash": record_hash}
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._sequence += 1
        self._previous_hash = record_hash
        return record

    @staticmethod
    def read_records(path: Path) -> Iterator[dict[str, Any]]:
        if not path.exists():
            return
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise HistoryIntegrityError(f"invalid JSON at line {line_number}") from exc

    @staticmethod
    def verify(records: list[dict[str, Any]]) -> str:
        previous = GENESIS_HASH
        for index, record in enumerate(records):
            if record.get("sequence") != index or record.get("previous_hash") != previous:
                raise HistoryIntegrityError(f"broken history chain at record {index}")
            body = {key: value for key, value in record.items() if key != "record_hash"}
            expected = hashlib.sha256(canonical_json(body).encode()).hexdigest()
            if record.get("record_hash") != expected:
                raise HistoryIntegrityError(f"modified history record {index}")
            previous = expected
        return previous
