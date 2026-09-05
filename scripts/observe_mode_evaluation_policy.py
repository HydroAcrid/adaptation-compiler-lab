"""Capability-free worker for one answer-blind Mode-evaluation policy call."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_SOURCE_LIMIT = 64 * 1024
_ALLOWED_STRING_METHODS = frozenset(
    {"casefold", "isdigit", "join", "lower", "replace", "split", "strip"}
)
_ALLOWED_BUILTINS = frozenset({"bool", "int", "len", "max", "min", "str", "ValueError"})
_FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "exit",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "open",
        "print",
        "quit",
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
    ast.AnnAssign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.Tuple,
    ast.List,
    ast.Set,
    ast.Dict,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.Call,
    ast.Attribute,
    ast.BinOp,
    ast.Add,
    ast.Sub,
)


def _tree(path: Path, required_function: str) -> ast.Module:
    raw = path.read_bytes()
    if len(raw) > _SOURCE_LIMIT:
        raise ValueError("solution source exceeded its ceiling")
    tree = ast.parse(raw.decode("utf-8"), filename=str(path))
    functions = {item.name: item for item in tree.body if isinstance(item, ast.FunctionDef)}
    if required_function not in functions:
        raise ValueError(f"solution omitted {required_function}")
    for item in tree.body:
        if (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        ):
            continue
        if not isinstance(item, ast.FunctionDef):
            raise ValueError("solution may contain only function definitions")
    for function in functions.values():
        if function.name.startswith("_") or function.decorator_list:
            raise ValueError("solution function declaration is not allowed")
        if function.args.vararg is not None or function.args.kwarg is not None:
            raise ValueError("solution variadic arguments are not allowed")
        function.returns = None
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ):
            argument.annotation = None
    allowed_calls = {*functions, *_ALLOWED_BUILTINS}
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"solution syntax is not allowed: {type(node).__name__}")
        if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id in _FORBIDDEN_NAMES):
            raise ValueError("solution name is not allowed")
        if isinstance(node, ast.Call):
            named_call = isinstance(node.func, ast.Name) and node.func.id in allowed_calls
            method_call = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _ALLOWED_STRING_METHODS
                and not node.keywords
            )
            if not named_call and not method_call:
                raise ValueError("solution call is not allowed")
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            if any(
                not isinstance(target, ast.Name)
                and not (
                    isinstance(target, ast.Tuple)
                    and all(isinstance(item, ast.Name) for item in target.elts)
                )
                for target in targets
            ):
                raise ValueError("solution assignment target is not allowed")
            if isinstance(node, ast.AnnAssign):
                node.annotation = ast.Constant(value=None)
    return ast.fix_missing_locations(tree)


def _load(workspace: Path, function_name: str) -> ModuleType:
    path = workspace / "src" / "solution.py"
    tree = _tree(path, function_name)
    module = ModuleType("_temper_mode_restricted_solution")
    module.__dict__["__builtins__"] = {
        "ValueError": ValueError,
        "bool": bool,
        "int": int,
        "len": len,
        "max": max,
        "min": min,
        "str": str,
    }
    sys.dont_write_bytecode = True
    exec(compile(tree, str(path), "exec"), module.__dict__, module.__dict__)
    return module


def _json_value(value: object) -> object:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return json.loads(encoded)


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
        raise ValueError("Mode scenario identity is invalid")
    if not isinstance(call_arguments, list):
        raise ValueError("Mode scenario arguments are invalid")
    try:
        module = _load(arguments.workspace, function_name)
        function = module.__dict__.get(function_name)
        if not callable(function):
            raise ValueError(f"solution omitted {function_name}")
        value = _json_value(function(*call_arguments))
        _emit(
            {
                "observation_version": "1.0.0",
                "scenario_id": scenario_id,
                "status": "returned",
                "value": value,
                "detail": None,
            }
        )
    except (MemoryError, SystemExit, KeyboardInterrupt):
        raise
    except Exception as error:
        _emit(
            {
                "observation_version": "1.0.0",
                "scenario_id": scenario_id,
                "status": "raised",
                "value": None,
                "detail": f"{type(error).__name__}: {error}",
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
