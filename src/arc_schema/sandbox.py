from __future__ import annotations

"""
受限沙箱：安全编译并执行模型生成的 world_model.py。

模型代码不可信，本模块用三层机制约束其能力：
1. AST 静态检查（_NodeGuard）：禁止 import、global/nonlocal、危险内置名与 dunder 属性访问；
2. builtins 白名单（_ALLOWED_BUILTINS）：exec 时只注入纯计算常用内置，且以只读 MappingProxyType 挂载；
3. 超时（run_with_timeout / SIGALRM）：限制墙钟执行时间，避免死循环拖死宿主。

阅读导引：
- validate_source / _NodeGuard：静态拒绝危险语法
- exec_world_model：编译执行并返回命名空间（含 step/predict/is_goal）
- 允许：纯计算 + 宿主注入的 helpers（GridState、np 等）
- 禁止：文件、网络、任意 import、dunder 反射

对外入口为 exec_world_model；违规统一为 SandboxError。
注意：应用级轻量沙箱，不是进程/容器隔离。
"""

import ast
import signal
from types import MappingProxyType
from typing import Any, Callable


class SandboxError(ValueError):
    """Raised when model code violates sandbox rules or fails to load."""


_FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "breakpoint",
        "memoryview",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "classmethod",
        "staticmethod",
        "property",
        "type",
        "help",
        "exit",
        "quit",
        "copyright",
        "credits",
        "license",
    }
)

_ALLOWED_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}


class _NodeGuard(ast.NodeVisitor):
    """AST 访问器：遇到 import / 危险名 / dunder 访问立即抛 SandboxError。"""

    def visit_Import(self, node: ast.Import) -> None:
        raise SandboxError("import statements are forbidden in world_model.py")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raise SandboxError("import statements are forbidden in world_model.py")

    def visit_Global(self, node: ast.Global) -> None:
        raise SandboxError("global statements are forbidden")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        raise SandboxError("nonlocal statements are forbidden")

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_NAMES:
            raise SandboxError(f"call to {node.func.id} is forbidden")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            raise SandboxError(f"access to dunder attribute {node.attr} is forbidden")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in _FORBIDDEN_NAMES:
            raise SandboxError(f"use of {node.id} is forbidden")
        self.generic_visit(node)


def validate_source(source: str) -> ast.Module:
    try:
        tree = ast.parse(source, filename="world_model.py", mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"syntax error: {exc}") from exc
    _NodeGuard().visit(tree)
    return tree


def _timeout_handler(signum: int, frame: Any) -> None:
    raise TimeoutError("sandboxed execution exceeded time limit")


def run_with_timeout(fn: Callable[[], Any], *, timeout_seconds: float) -> Any:
    """Best-effort wall-clock timeout using SIGALRM (Unix)."""
    if timeout_seconds <= 0:
        return fn()
    if not hasattr(signal, "SIGALRM"):
        return fn()
    previous = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def exec_world_model(
    source: str,
    *,
    helpers: dict[str, Any] | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """
    在受限命名空间中编译并执行模型撰写的 world_model.py。

    返回模块全局（含模型定义的函数）；失败统一包装为 SandboxError。
    """
    tree = validate_source(source)
    code = compile(tree, "world_model.py", "exec")
    namespace: dict[str, Any] = {"__builtins__": MappingProxyType(_ALLOWED_BUILTINS)}
    if helpers:
        namespace.update(helpers)

    def _run() -> None:
        exec(code, namespace, namespace)  # noqa: S102 — intentional sandboxed exec

    try:
        run_with_timeout(_run, timeout_seconds=timeout_seconds)
    except TimeoutError as exc:
        raise SandboxError(str(exc)) from exc
    except SandboxError:
        raise
    except Exception as exc:  # model code runtime errors
        raise SandboxError(f"world model failed during load: {type(exc).__name__}: {exc}") from exc
    return namespace
