"""Boundaries for the one-shot curated Systematic Debugger screen."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from adaptation_compiler_lab.modes.evaluation import run_bounded_mode_policy_observation
from adaptation_compiler_lab.modes.foundry_execution import FoundryTrialResultV1
from scripts.freeze_foundry_systematic_debugger import build_contract

ROOT = Path(__file__).resolve().parents[3]
OBSERVER = ROOT / "scripts" / "observe_foundry_debug_policy.py"


def test_foundry_contract_is_exactly_bounded_and_hidden_cases_stay_outside_tasks() -> None:
    contract = build_contract(ROOT)

    assert contract.target_runs == 8
    assert contract.target_model == "gpt-5.6-luna"
    assert contract.target_reasoning_effort == "medium"
    assert contract.provider_billed_calls == 0
    assert contract.api_keys_allowed is False
    assert contract.external_validation_accessed is False
    assert [item.kind for item in contract.fixtures] == [
        "diagnostic",
        "diagnostic",
        "neutral_control",
    ]
    for fixture in contract.fixtures:
        root = ROOT / "development_benchmark_curated_modes" / fixture.fixture_directory
        serialized_tree = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py"))
        )
        assert not any(scenario.scenario_id in serialized_tree for scenario in fixture.scenarios)


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.geteuid() == 0 or shutil.which("bwrap") is None,
    reason="the answer-blind scorer requires unprivileged Linux bubblewrap",
)
def test_hidden_observer_detects_the_deliberate_fixture_defects() -> None:
    contract = build_contract(ROOT)
    observed_counts: dict[str, int] = {}

    for fixture in contract.fixtures:
        workspace = ROOT / "development_benchmark_curated_modes" / fixture.fixture_directory
        passed = 0
        for scenario in fixture.scenarios:
            observation, receipt = run_bounded_mode_policy_observation(
                observer_script=OBSERVER,
                workspace=workspace,
                scenario=scenario,
                function_name=fixture.function_name,
            )
            assert receipt.status == "succeeded"
            passed += int(
                observation is not None
                and observation.status == "returned"
                and observation.value == scenario.expected
            )
        observed_counts[fixture.task_id] = passed

    assert observed_counts == {
        "foundry-debug-01-shared-state": 1,
        "foundry-debug-02-failed-fix": 1,
        "foundry-debug-04-neutral-copy": 1,
    }


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.geteuid() == 0 or shutil.which("bwrap") is None,
    reason="the answer-blind scorer requires unprivileged Linux bubblewrap",
)
def test_hidden_observer_accepts_a_standard_deepcopy_root_cause_repair(tmp_path: Path) -> None:
    contract = build_contract(ROOT)
    fixture = next(item for item in contract.fixtures if item.task_id.endswith("failed-fix"))
    source = tmp_path / "src"
    source.mkdir()
    (source / "solution.py").write_text(
        '''"""Construct delivery policies for two independent jobs."""

from copy import deepcopy

def build_policy_pair(
    first_job, first_headers, first_retry, second_job, second_headers, second_retry
):
    if not first_job or not second_job:
        raise ValueError("job_id is required")
    template = {"headers": {"Accept": "application/json"}, "retry_delays": []}
    first = deepcopy(template)
    first["job_id"] = first_job
    first["headers"].update(first_headers)
    if first_retry is not None:
        if first_retry < 0:
            raise ValueError("retry_delay cannot be negative")
        first["retry_delays"].append(first_retry)
    second = deepcopy(template)
    second["job_id"] = second_job
    second["headers"].update(second_headers)
    if second_retry is not None:
        if second_retry < 0:
            raise ValueError("retry_delay cannot be negative")
        second["retry_delays"].append(second_retry)
    return first, second
''',
        encoding="utf-8",
    )

    for scenario in fixture.scenarios:
        observation, receipt = run_bounded_mode_policy_observation(
            observer_script=OBSERVER,
            workspace=tmp_path,
            scenario=scenario,
            function_name=fixture.function_name,
        )
        assert receipt.status == "succeeded"
        assert observation is not None
        assert observation.status == "returned"
        assert observation.value == scenario.expected


def _trial(*, run_id: str, task_id: str, task_kind: str, condition: str) -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    return {
        "run_id": run_id,
        "task_id": task_id,
        "task_kind": task_kind,
        "condition": condition,
        "contract_digest": digest,
        "source_commit": "b" * 40,
        "trace_digest": digest,
        "diff_digest": digest,
        "final_response_digest": digest,
        "command_digest": digest,
        "environment_digest": digest,
        "encrypted_trace_ref": digest,
        "hidden_checks_passed": 3,
        "hidden_checks_total": 3,
        "visible_tests_passed": True,
        "focused_reproduction_observed": task_kind == "diagnostic",
        "regression_command_observed": True,
        "behavior_conformant": True,
        "integrity_valid": True,
        "duration_seconds": 1.0,
        "input_tokens": 1,
        "cached_input_tokens": 0,
        "output_tokens": 1,
        "reasoning_output_tokens": 0,
        "workspace_destroyed": True,
    }


def test_trial_rejects_a_debugging_state_on_a_neutral_control() -> None:
    payload = _trial(
        run_id="run-neutral",
        task_id="neutral-task",
        task_kind="neutral_control",
        condition="core_only",
    )
    payload["focused_reproduction_observed"] = False

    with pytest.raises(ValueError, match="neutral control"):
        FoundryTrialResultV1.model_validate(payload)
