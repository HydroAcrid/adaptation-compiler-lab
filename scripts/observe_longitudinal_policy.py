"""Trusted wrapper around one answer-blind longitudinal policy worker."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

_WORKER_OUTPUT_LIMIT = 64 * 1024
_POLICY_SOURCE_LIMIT = 64 * 1024
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
_ALLOWED_POLICY_NODES = (
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
    ast.Delete,
    ast.Assign,
    ast.AnnAssign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Del,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.Tuple,
    ast.List,
    ast.Set,
    ast.Dict,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.Call,
)


def _literal_default(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bool, int, float, type(None)))
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_literal_default(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            key is not None and _literal_default(key) and _literal_default(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    return False


def _validated_policy_tree(path: Path) -> ast.Module:
    """Return a capability-free policy AST or reject it before execution."""

    source = path.read_bytes()
    if len(source) > _POLICY_SOURCE_LIMIT:
        raise ValueError("longitudinal policy source exceeded its ceiling")
    tree = ast.parse(source.decode("utf-8"), filename=str(path))
    functions = {item.name: item for item in tree.body if isinstance(item, ast.FunctionDef)}
    if not {"choose_publish_action", "build_publish_plan"} & set(functions):
        raise ValueError("longitudinal policy omitted its required function")
    for item in tree.body:
        if (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        ):
            continue
        if not isinstance(item, ast.FunctionDef):
            raise ValueError("longitudinal policy may contain only function definitions")
    for function in functions.values():
        if (
            function.name.startswith("_")
            or function.name in _FORBIDDEN_NAMES
            or function.decorator_list
            or function.args.vararg is not None
            or function.args.kwarg is not None
        ):
            raise ValueError("longitudinal policy function declaration is not allowed")
        defaults = (*function.args.defaults, *function.args.kw_defaults)
        if any(item is not None and not _literal_default(item) for item in defaults):
            raise ValueError("longitudinal policy defaults must be literal values")
        function.returns = None
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ):
            if argument.arg.startswith("_") or argument.arg in _FORBIDDEN_NAMES:
                raise ValueError("longitudinal policy argument name is not allowed")
            argument.annotation = None
    allowed_calls = {*functions, "ValueError"}
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_POLICY_NODES):
            raise ValueError(f"longitudinal policy syntax is not allowed: {type(node).__name__}")
        if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id in _FORBIDDEN_NAMES):
            raise ValueError("longitudinal policy name is not allowed")
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name)
            or node.func.id not in allowed_calls
            or node.keywords
        ):
            raise ValueError("longitudinal policy call is not allowed")
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            if any(not isinstance(target, ast.Name) for target in targets):
                raise ValueError("longitudinal policy assignment target is not allowed")
            if isinstance(node, ast.AnnAssign):
                node.annotation = ast.Constant(value=None)
    return ast.fix_missing_locations(tree)


def _load_policy(workspace: Path) -> ModuleType:
    path = workspace / "policy.py"
    if not path.is_file():
        raise ValueError("longitudinal workspace is missing policy.py")
    tree = _validated_policy_tree(path)
    specification = importlib.util.spec_from_loader(
        "_acl_longitudinal_restricted_policy",
        loader=None,
    )
    if specification is None:
        raise ValueError("longitudinal policy module could not be prepared")
    module = importlib.util.module_from_spec(specification)
    sys.dont_write_bytecode = True
    module.__dict__["__builtins__"] = {"ValueError": ValueError}
    exec(compile(tree, str(path), "exec"), module.__dict__, module.__dict__)
    return module


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _worker(workspace: Path, call: dict[str, Any]) -> int:
    try:
        module = _load_policy(workspace)
        function_name = (
            "choose_publish_action" if call["task_kind"] == "action" else "build_publish_plan"
        )
        function = getattr(module, function_name, None)
        if not callable(function):
            raise ValueError(f"policy omitted {function_name}")
        raw = function(call["destination_exists"], call["backup_requested"])
        if call["task_kind"] == "action":
            if not isinstance(raw, str):
                raise ValueError("action policy must return str")
            value: str | list[str] = raw
        else:
            if not isinstance(raw, tuple) or not all(isinstance(item, str) for item in raw):
                raise ValueError("plan policy must return tuple[str, ...]")
            value = list(raw)
        _emit(
            {
                "detail": None,
                "status": "returned",
                "value": value,
                "worker_version": "1.0.0",
            }
        )
    except Exception as error:
        _emit(
            {
                "detail": f"{type(error).__name__}: {error}",
                "status": "raised",
                "value": None,
                "worker_version": "1.0.0",
            }
        )
    return 0


def _observe(workspace: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    call = {
        "backup_requested": scenario["backup_requested"],
        "destination_exists": scenario["destination_exists"],
        "task_kind": scenario["task_kind"],
    }
    with tempfile.TemporaryDirectory(prefix="acl-longitudinal-policy-worker-") as temporary:
        root = Path(temporary)
        stdout_path = root / "stdout.bin"
        stderr_path = root / "stderr.bin"
        with stdout_path.open("w+b") as stdout_stream, stderr_path.open("w+b") as stderr_stream:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--workspace",
                    str(workspace),
                    "--scenario-json",
                    json.dumps(call, sort_keys=True, separators=(",", ":")),
                ],
                check=False,
                cwd=workspace,
                env={
                    "HOME": "/workspace",
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "PATH": "/usr/bin:/bin",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "TMPDIR": "/tmp",
                },
                stdin=subprocess.DEVNULL,
                stdout=stdout_stream,
                stderr=stderr_stream,
            )
            stdout_stream.seek(0)
            stderr_stream.seek(0)
            stdout = stdout_stream.read(_WORKER_OUTPUT_LIMIT + 1)
            stderr = stderr_stream.read(_WORKER_OUTPUT_LIMIT + 1)
    if completed.returncode != 0:
        return {
            "detail": f"policy worker exited with code {completed.returncode}",
            "status": "raised",
            "value": None,
        }
    if len(stdout) > _WORKER_OUTPUT_LIMIT or len(stderr) > _WORKER_OUTPUT_LIMIT:
        return {
            "detail": "policy worker output exceeded its ceiling",
            "status": "raised",
            "value": None,
        }
    try:
        payload = json.loads(stdout.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {
            "detail",
            "status",
            "value",
            "worker_version",
        }:
            raise ValueError("policy worker payload fields are invalid")
        if payload["worker_version"] != "1.0.0":
            raise ValueError("policy worker version is invalid")
        status = payload["status"]
        value = payload["value"]
        detail = payload["detail"]
        if status == "returned":
            if scenario["task_kind"] == "action":
                if not isinstance(value, str):
                    raise ValueError("returned action is invalid")
            elif not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError("returned plan is invalid")
        elif status == "raised":
            if value is not None or not isinstance(detail, str):
                raise ValueError("failed policy observation is invalid")
        else:
            raise ValueError("policy worker status is invalid")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        return {
            "detail": f"{type(error).__name__}: {error}",
            "status": "raised",
            "value": None,
        }
    return {"detail": detail, "status": status, "value": value}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scenario-json", required=True)
    arguments = parser.parse_args()
    scenario = json.loads(arguments.scenario_json)
    workspace = arguments.workspace.resolve()
    if arguments.worker:
        return _worker(workspace, scenario)
    observed = _observe(workspace, scenario)
    _emit(
        {
            "detail": observed["detail"],
            "observation_version": "1.0.0",
            "scenario_id": scenario["scenario_id"],
            "status": observed["status"],
            "value": observed["value"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
