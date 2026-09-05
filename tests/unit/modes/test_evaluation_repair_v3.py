"""The Mode v3 repair is distinct, mechanically bounded, and smoke-gated."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationPublicPlanV1,
    load_mode_evaluation_contract,
    load_mode_evaluation_fixture,
)
from adaptation_compiler_lab.serialization import canonical_digest
from scripts.mode_evaluation_v3_common import (
    code_mode_host_digest,
    instrument_source_digests,
    load_object,
    require_valid_smoke,
    verify_scorer_runtime,
)

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "development_benchmark_mode_evaluation"


def test_v1_failure_is_preserved_unjudged_and_non_evidentiary() -> None:
    report = load_object(BENCHMARK / "results-v1/blind-trial-report.json")
    completion = load_object(BENCHMARK / "results-v1/completion.json")
    trials = report["trials"]

    assert isinstance(trials, list)
    assert len(trials) == 30
    typed_trials = [item for item in trials if isinstance(item, dict)]
    assert len(typed_trials) == 30
    assert report["all_trial_integrity_valid"] is False
    assert all(item["integrity_valid"] is False for item in typed_trials)
    assert completion["report_digest"] == canonical_digest(report)
    assert not (BENCHMARK / "results-v1/judges").exists()
    assert not (BENCHMARK / "results-v1/unblinded-result.json").exists()


def test_v2_smoke_failure_is_preserved_and_did_not_admit_the_grid() -> None:
    smoke = load_object(BENCHMARK / "smoke-v2/smoke-receipt.json")
    completion = load_object(BENCHMARK / "smoke-v2/completion.json")

    assert smoke["valid"] is False
    assert smoke["workspace_destroyed"] is True
    assert smoke["provider_billed_calls"] == 0
    assert completion["smoke_receipt_digest"] == canonical_digest(smoke)
    assert not (BENCHMARK / "results-v2").exists()


def test_v3_changes_instrument_mechanics_but_not_modes_or_tasks() -> None:
    v2 = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v2.json")
    v3 = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v3.json")

    assert v3.catalog_design_digests == v2.catalog_design_digests
    assert v3.fixtures == v2.fixtures
    assert v3.target_cli_version == v2.target_cli_version
    assert v3.target_model == v2.target_model
    assert v3.target_reasoning_effort == v2.target_reasoning_effort
    assert v3.runner_source_digest != v2.runner_source_digest
    assert v3.scorer_source_digest != v2.scorer_source_digest


def test_v3_contract_binds_complete_repair_source_bundles() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v3.json")

    for field, digest in instrument_source_digests(ROOT).items():
        assert getattr(contract, field) == digest


def test_v3_public_plan_is_complete_and_condition_blind() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v3.json")
    plan = ModeEvaluationPublicPlanV1.model_validate_json(
        (BENCHMARK / "PUBLIC_PLAN-v3.json").read_text(encoding="utf-8"), strict=True
    )

    assert plan.contract_digest == contract.content_digest
    assert len(plan.run_order) == 30
    assert "core-only" not in plan.model_dump_json()
    assert "core-plus-mode" not in plan.model_dump_json()


def test_v3_repair_protocol_binds_both_mechanical_repairs() -> None:
    repair = load_object(BENCHMARK / "REPAIR_PROTOCOL-v3.json")
    preregistration = load_object(BENCHMARK / "PREREGISTRATION-v3.json")

    assert repair["mode_content_changed"] is False
    assert repair["task_content_changed"] is False
    assert repair["target_smoke_required"] is True
    assert repair["scorer_smoke_required"] is True
    assert repair["target_code_mode_host"] == "pinned_companion_mounted_inside_outer_bubblewrap"
    assert repair["scorer_invocation_path_preserved"] is True
    assert repair["code_mode_host_digest"] == code_mode_host_digest(ROOT)
    assert preregistration["repair_protocol_digest"] == canonical_digest(repair)


def test_v3_grid_fails_closed_without_a_passing_smoke(tmp_path: Path) -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v3.json")

    with pytest.raises(RuntimeError, match="invalid Mode evaluation v3 file"):
        require_valid_smoke(benchmark=tmp_path, contract=contract)


def test_v3_scorer_runtime_probe_rejects_a_missing_interpreter() -> None:
    with pytest.raises(RuntimeError, match="external and executable"):
        verify_scorer_runtime(repo=ROOT, python=ROOT / "missing-python")


def test_v3_live_smoke_fixture_really_requires_an_edit() -> None:
    fixture = load_mode_evaluation_fixture(BENCHMARK / "tasks/mode-v2-smoke.json")
    module_path = BENCHMARK / fixture.fixture_directory / "src/solution.py"
    spec = importlib.util.spec_from_file_location("mode_v3_smoke_solution", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.clamp_attempts(2, 5) == 5
    assert fixture.scenarios[0].expected == 1
