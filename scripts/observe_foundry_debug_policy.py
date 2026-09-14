"""Capability-free observer for Foundry debugging fixtures."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

_SOURCE_LIMIT = 64 * 1024
_ALLOWED_METHODS = frozenset({"append", "copy", "extend", "strip", "update"})
_ALLOWED_BUILTINS = frozenset({"deepcopy", "dict", "len", "list", "str", "tuple", "ValueError"})
_FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "print",
        "setattr",
        "vars",
    }
)
_ALLOWED_NODES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Expr,
    ast.Constant,
    ast.If,
    ast.IfExp,
    ast.Return,
    ast.Raise,
    ast.Assign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.Gt,
    ast.In,
    ast.Is,
    ast.IsNot,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.Tuple,
    ast.List,
    ast.Dict,
    ast.Subscript,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.Call,
    ast.Attribute,
)


def _tree(path: Path, required_function: str) -> ast.Module:
    raw = path.read_bytes()
    if len(raw) > _SOURCE_LIMIT:
        raise ValueError("solution source exceeded its ceiling")
    tree = ast.parse(raw.decode("utf-8"), filename=str(path))
    functions = {item.name: item for item in tree.body if isinstance(item, ast.FunctionDef)}
    if set(functions) != {required_function}:
        raise ValueError("solution must contain exactly the requested public function")
    imports = tuple(item for item in tree.body if isinstance(item, ast.ImportFrom))
    if any(
        item.module != "copy"
        or item.level != 0
        or len(item.names) != 1
        or item.names[0].name != "deepcopy"
        or item.names[0].asname is not None
        for item in imports
    ):
        raise ValueError("solution imports are not allowed")
    for item in tree.body:
        module_docstring = (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        )
        if not module_docstring and not isinstance(item, ast.FunctionDef) and item not in imports:
            raise ValueError("solution may contain only its docstring and requested function")
    tree.body = [item for item in tree.body if item not in imports]
    function = functions[required_function]
    if function.decorator_list or function.args.vararg or function.args.kwarg:
        raise ValueError("solution function declaration is not allowed")
    function.returns = None
    for argument in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs):
        argument.annotation = None
    allowed_calls = {*_ALLOWED_BUILTINS, required_function}
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"solution syntax is not allowed: {type(node).__name__}")
        if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id in _FORBIDDEN_NAMES):
            raise ValueError("solution name is not allowed")
        if isinstance(node, ast.Call):
            named = isinstance(node.func, ast.Name) and node.func.id in allowed_calls
            method = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _ALLOWED_METHODS
                and not node.keywords
            )
            if not named and not method:
                raise ValueError("solution call is not allowed")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                safe_target = isinstance(target, ast.Name) or (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                )
                if not safe_target:
                    raise ValueError("solution assignment target is not allowed")
    return ast.fix_missing_locations(tree)


def _load(workspace: Path, function_name: str) -> ModuleType:
    path = workspace / "src" / "solution.py"
    tree = _tree(path, function_name)
    module = ModuleType("_temper_foundry_restricted_solution")
    module.__dict__["__builtins__"] = {
        "ValueError": ValueError,
        "deepcopy": deepcopy,
        "dict": dict,
        "len": len,
        "list": list,
        "str": str,
        "tuple": tuple,
    }
    module.__dict__["deepcopy"] = deepcopy
    sys.dont_write_bytecode = True
    exec(compile(tree, str(path), "exec"), module.__dict__, module.__dict__)
    return module


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scenario-json", required=True)
    arguments = parser.parse_args()
    scenario: dict[str, Any] = json.loads(arguments.scenario_json)
    scenario_id = scenario.get("scenario_id")
    function_name = scenario.get("function_name")
    call_arguments = scenario.get("arguments")
    if not isinstance(scenario_id, str) or not isinstance(function_name, str):
        raise ValueError("Foundry scenario identity is invalid")
    if not isinstance(call_arguments, list):
        raise ValueError("Foundry scenario arguments are invalid")
    try:
        function = _load(arguments.workspace, function_name).__dict__.get(function_name)
        if not callable(function):
            raise ValueError(f"solution omitted {function_name}")
        value = json.loads(json.dumps(function(*call_arguments), ensure_ascii=False))
        _emit(
            {
                "detail": None,
                "observation_version": "1.0.0",
                "scenario_id": scenario_id,
                "status": "returned",
                "value": value,
            }
        )
    except (MemoryError, SystemExit, KeyboardInterrupt):
        raise
    except Exception as error:
        _emit(
            {
                "detail": f"{type(error).__name__}: {error}",
                "observation_version": "1.0.0",
                "scenario_id": scenario_id,
                "status": "raised",
                "value": None,
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
