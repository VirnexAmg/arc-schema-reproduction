from __future__ import annotations

"""
单次运行的持久 Workspace：落地 world_model.py + notes.md，并跟踪认证状态。

本模块是 agent 改代码与 ProgramWorldModel 执行之间的薄适配层：
1. 初始化时确保目录与默认 stub/笔记存在；
2. write_code 整文件写入并重载模型；apply_patch 要求唯一子串替换后走同一写路径；
3. 任何代码变更都会 version+1、清除 certified/last_backtest，强制重新回测；
4. model() 缓存已加载的 ProgramWorldModel；record_mismatch 记录失败现场并取消认证。

回测通过后的 certified=True 由上层（如 deliberation）设置；本文件只保证「改码即失效」。
"""

from dataclasses import dataclass, field
from pathlib import Path

from arc_schema.program_world_model import (
    DEFAULT_WORLD_MODEL_STUB,
    ProgramBacktestResult,
    ProgramWorldModel,
)


@dataclass
class Workspace:
    """一次运行的持久 Schema 记忆：world_model.py + notes.md。"""

    root: Path
    version: int = 0
    last_backtest: ProgramBacktestResult | None = None
    certified: bool = False
    last_mismatch: dict | None = None
    _model: ProgramWorldModel | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.world_model_path.exists():
            self.write_code(DEFAULT_WORLD_MODEL_STUB)
        if not self.notes_path.exists():
            self.notes_path.write_text(
                "# Working notes\nInfer objects and mechanisms from transitions only.\n",
                encoding="utf-8",
            )

    @property
    def world_model_path(self) -> Path:
        return self.root / "world_model.py"

    @property
    def notes_path(self) -> Path:
        return self.root / "notes.md"

    def read_code(self) -> str:
        return self.world_model_path.read_text(encoding="utf-8")

    def read_notes(self) -> str:
        return self.notes_path.read_text(encoding="utf-8")

    def write_notes(self, text: str) -> None:
        self.notes_path.write_text(text, encoding="utf-8")

    def write_code(self, source: str) -> ProgramWorldModel:
        """整文件覆盖 world_model.py，使认证失效并重新沙箱加载模型。"""
        self.world_model_path.write_text(source, encoding="utf-8")
        self.version += 1
        self.certified = False
        self.last_backtest = None
        self._model = ProgramWorldModel(source)
        return self._model

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
        """记录预测与真实不一致的载荷，并取消认证。"""
        self.last_mismatch = payload
        self.certified = False
