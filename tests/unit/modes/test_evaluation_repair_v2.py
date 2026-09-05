"""The Mode v2 repair is distinct, mechanically bounded, and smoke-gated."""

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
from scripts.mode_evaluation_v2_common import (
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


def test_v2_changes_instrument_mechanics_but_not_modes_or_tasks() -> None:
    v1 = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v1.json")
    v2 = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v2.json")

    assert v2.catalog_design_digests == v1.catalog_design_digests
    assert v2.fixtures == v1.fixtures
    assert v2.target_cli_version == v1.target_cli_version
    assert v2.target_model == v1.target_model
    assert v2.target_reasoning_effort == v1.target_reasoning_effort
    assert v2.runner_source_digest != v1.runner_source_digest
    assert v2.scorer_source_digest != v1.scorer_source_digest


def test_v2_contract_preserves_its_frozen_repair_source_digests() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v2.json")

    assert contract.runner_source_digest == (
        "sha256:486ce6298bf7e295c7dc2113cdf7a8a0c07347da4dfa6f0799e1806ca3ca32c4"
    )
    assert contract.scorer_source_digest == (
        "sha256:1c363f3ccacc91e6810a1b9895935249c603f2624feb26d2bab9ca509155ccba"
    )
    assert contract.observer_source_digest == (
        "sha256:60ce84008fa7ff1941f32d8768e474cce4a7c2ea9d401132ac3fc840da932737"
    )
    assert contract.judge_role_runner_source_digest == (
        "sha256:6c1f9eee06b1bb5b410df5a86e013303e64ad210b65f13af57cb0c0b4bea18cc"
    )
    assert contract.judge_source_digest == (
        "sha256:aeadec37672c7aca0365a03304725df117527f05a9436ff879029d7544c486e4"
    )
    assert contract.unblind_source_digest == (
        "sha256:f4a20b40bc22ec0da9566d98155e67ebec8624d1fb8b0e6ddb14a98c6b6c52ab"
    )


def test_v2_public_plan_is_complete_and_condition_blind() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v2.json")
    plan = ModeEvaluationPublicPlanV1.model_validate_json(
        (BENCHMARK / "PUBLIC_PLAN-v2.json").read_text(encoding="utf-8"), strict=True
    )

    assert plan.contract_digest == contract.content_digest
    assert len(plan.run_order) == 30
    assert "core-only" not in plan.model_dump_json()
    assert "core-plus-mode" not in plan.model_dump_json()


def test_v2_repair_protocol_requires_both_smokes_and_no_content_change() -> None:
    repair = load_object(BENCHMARK / "REPAIR_PROTOCOL-v2.json")
    preregistration = load_object(BENCHMARK / "PREREGISTRATION-v2.json")

    assert repair["mode_content_changed"] is False
    assert repair["task_content_changed"] is False
    assert repair["target_smoke_required"] is True
    assert repair["scorer_smoke_required"] is True
    assert repair["target_code_mode_host"] == "enabled_inside_outer_bubblewrap"
    assert preregistration["repair_protocol_digest"] == canonical_digest(repair)


def test_v2_grid_fails_closed_without_a_passing_smoke(tmp_path: Path) -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v2.json")

    with pytest.raises(RuntimeError, match="invalid Mode evaluation v2 file"):
        require_valid_smoke(benchmark=tmp_path, contract=contract)


def test_v2_scorer_runtime_probe_rejects_a_missing_interpreter() -> None:
    with pytest.raises(RuntimeError, match="external and executable"):
        verify_scorer_runtime(repo=ROOT, python=ROOT / "missing-python")


def test_v2_live_smoke_fixture_really_requires_an_edit() -> None:
    fixture = load_mode_evaluation_fixture(BENCHMARK / "tasks/mode-v2-smoke.json")
    module_path = BENCHMARK / fixture.fixture_directory / "src/solution.py"
    spec = importlib.util.spec_from_file_location("mode_v2_smoke_solution", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.clamp_attempts(2, 5) == 5
    assert fixture.scenarios[0].expected == 1
