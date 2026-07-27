"""Answer-blind worker that observes one generated policy call."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_policy(workspace: Path) -> ModuleType:
    path = workspace / "deployment_policy.py"
    specification = importlib.util.spec_from_file_location(
        "_acl_compact_observed_policy",
        path,
    )
    if specification is None or specification.loader is None:
        raise ValueError("deployment_policy.py could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.dont_write_bytecode = True
    specification.loader.exec_module(module)
    return module


def _emit(value: dict[str, Any]) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scenario-json", required=True)
    arguments = parser.parse_args()
    scenario = json.loads(arguments.scenario_json)
    scenario_id = scenario["scenario_id"]
    try:
        module = _load_policy(arguments.workspace.resolve())
        function = getattr(module, "plan_delivery", None)
        if not callable(function):
            raise ValueError("deployment policy omitted plan_delivery")
        raw = function(
            scenario["destination_exists"],
            scenario["storage_class"],
            scenario["recovery_copy_approved"],
        )
        if not isinstance(raw, tuple) or not all(isinstance(item, str) for item in raw):
            _emit(
                {
                    "detail": "plan_delivery must return tuple[str, ...]",
                    "observation_version": "1.0.0",
                    "scenario_id": scenario_id,
                    "status": "invalid_return",
                    "value": None,
                }
            )
            return 0
        _emit(
            {
                "detail": None,
                "observation_version": "1.0.0",
                "scenario_id": scenario_id,
                "status": "returned",
                "value": list(raw),
            }
        )
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
