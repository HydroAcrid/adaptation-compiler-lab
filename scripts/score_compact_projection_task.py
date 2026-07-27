"""Independent stdlib-only scorer for one fresh compact-projection task."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_policy(workspace: Path, task_id: str) -> ModuleType:
    path = workspace / "deployment_policy.py"
    specification = importlib.util.spec_from_file_location(
        "_acl_compact_" + task_id.replace("-", "_"),
        path,
    )
    if specification is None or specification.loader is None:
        raise ValueError("deployment_policy.py could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.dont_write_bytecode = True
    specification.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()

    manifest = json.loads(arguments.task_manifest.read_text(encoding="utf-8"))
    task_id = manifest["task_id"]
    module = _load_policy(arguments.workspace.resolve(), task_id)
    function = getattr(module, "plan_delivery", None)
    if not callable(function):
        raise ValueError("deployment policy omitted plan_delivery")
    groups: dict[str, dict[str, bool]] = {
        "diagnostic": {},
        "neutral": {},
        "objective": {},
    }
    observed: dict[str, str] = {}
    for scenario in manifest["scenarios"]:
        scenario_id = scenario["scenario_id"]
        try:
            raw = function(
                scenario["destination_exists"],
                scenario["storage_class"],
                scenario["recovery_copy_approved"],
            )
            value = tuple(raw) if isinstance(raw, (list, tuple)) else (str(raw),)
            observed[scenario_id] = repr(value)
            passed = value == tuple(scenario["expected_plan"])
        except Exception as error:
            observed[scenario_id] = f"{type(error).__name__}: {error}"
            passed = False
        groups[scenario["metric"]][scenario_id] = passed
    print(
        json.dumps(
            {"checks": groups, "observed": observed, "task_id": task_id},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
