"""Trusted wrapper around one answer-blind longitudinal policy worker."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

_WORKER_OUTPUT_LIMIT = 64 * 1024


def _load_policy(workspace: Path) -> ModuleType:
    path = workspace / "policy.py"
    if not path.is_file():
        raise ValueError("longitudinal workspace is missing policy.py")
    specification = importlib.util.spec_from_file_location(
        "_acl_longitudinal_untrusted_policy",
        path,
    )
    if specification is None or specification.loader is None:
        raise ValueError("longitudinal policy module could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.dont_write_bytecode = True
    specification.loader.exec_module(module)
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
