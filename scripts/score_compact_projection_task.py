"""Trusted scorer coordinator for one fresh compact-projection task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
    run_bounded_compact_policy_observation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()

    manifest = json.loads(arguments.task_manifest.read_text(encoding="utf-8"))
    task_id = manifest["task_id"]
    observer_script = Path(__file__).with_name("observe_compact_projection_policy.py")
    groups: dict[str, dict[str, bool]] = {
        "diagnostic": {},
        "neutral": {},
        "objective": {},
    }
    observed: dict[str, str] = {}
    receipts: dict[str, dict[str, object]] = {}
    for scenario in manifest["scenarios"]:
        scenario_id = scenario["scenario_id"]
        result = run_bounded_compact_policy_observation(
            observer_script=observer_script,
            workspace=arguments.workspace.resolve(),
            scenario_id=scenario_id,
            destination_exists=scenario["destination_exists"],
            storage_class=scenario["storage_class"],
            recovery_copy_approved=scenario["recovery_copy_approved"],
            timeout_seconds=2,
        )
        observation = result.observation
        receipts[scenario_id] = result.receipt.model_dump(
            mode="json",
            round_trip=True,
        )
        if observation is not None and observation.status == "returned":
            value = observation.value
            observed[scenario_id] = repr(value)
            passed = value == tuple(scenario["expected_plan"])
        else:
            detail = (
                observation.detail if observation is not None else result.receipt.failure_reason
            )
            observed[scenario_id] = (
                f"{observation.status if observation is not None else result.receipt.status}: "
                f"{detail}"
            )
            passed = False
        groups[scenario["metric"]][scenario_id] = passed
    print(
        json.dumps(
            {
                "checks": groups,
                "observed": observed,
                "receipts": receipts,
                "task_id": task_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
