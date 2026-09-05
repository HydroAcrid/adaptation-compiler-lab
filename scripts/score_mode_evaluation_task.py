"""Independent hidden scorer for one frozen Mode-evaluation task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.modes.evaluation import (
    load_mode_evaluation_fixture,
    run_bounded_mode_policy_observation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()
    fixture = load_mode_evaluation_fixture(arguments.task_manifest)
    observer = Path(__file__).with_name("observe_mode_evaluation_policy.py")
    checks: dict[str, dict[str, bool]] = {"diagnostic": {}, "neutral": {}}
    observations: dict[str, object] = {}
    receipts: dict[str, object] = {}
    for scenario in fixture.scenarios:
        observation, receipt = run_bounded_mode_policy_observation(
            observer_script=observer,
            workspace=arguments.workspace.resolve(),
            scenario=scenario,
            function_name=fixture.function_name,
        )
        passed = (
            observation is not None
            and observation.status == "returned"
            and observation.value == scenario.expected
        )
        checks[scenario.metric][scenario.scenario_id] = passed
        observations[scenario.scenario_id] = (
            observation.model_dump(mode="json") if observation is not None else None
        )
        receipts[scenario.scenario_id] = receipt.model_dump(mode="json")
    print(
        json.dumps(
            {
                "checks": checks,
                "observations": observations,
                "receipts": receipts,
                "task_id": fixture.task_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
