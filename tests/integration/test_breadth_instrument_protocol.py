from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentPublicPlan,
    load_breadth_instrument_contract,
    load_breadth_instrument_design,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.connectors.pins import sha256_file


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_breadth_instrument_repair"


def test_clean_breadth_design_and_contract_are_frozen() -> None:
    design = load_breadth_instrument_design(_root())
    contract = load_breadth_instrument_contract(_root(), design=design)

    assert {item.task.family for item in design.tasks} == set(ApprovedSourceFamily)
    assert design.compiled_material_bytes == 885
    assert design.profile_material_bytes == 986
    assert design.compiled_material_bytes < design.profile_material_bytes
    assert design.eligible_evidence_unchanged
    assert design.profile_material_unchanged
    assert design.compiled_change_kind == "expression_strength_only"
    assert design.maximum_subscription_sessions == 9
    assert contract.target_model == "gpt-5.6-luna"
    assert contract.target_reasoning_effort == "medium"
    assert contract.judge_model == "gpt-5.6-sol"
    assert contract.judge_reasoning_effort == "xhigh"


def test_public_plan_withholds_exact_condition_mapping() -> None:
    public = BreadthInstrumentPublicPlan.model_validate_json(
        (_root() / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    payload = json.loads((_root() / "PUBLIC_PLAN-v1.json").read_text(encoding="utf-8"))

    assert public.condition_mapping_withheld
    assert len(public.run_order) == 8
    assert len({cell.task_id for cell in public.run_order}) == 4
    assert len({cell.blind_condition_id for cell in public.run_order}) == 2
    assert "compiled_adaptation" not in json.dumps(payload)
    assert "strong_static_profile" not in json.dumps(payload)


def test_failed_results_are_digest_bound_and_preserved() -> None:
    design = load_breadth_instrument_design(_root())

    assert design.original_failed_result_digest == sha256_file(
        _repo() / "development_benchmark_breadth_replication/results-v1/unblinded-result.json"
    )
    assert design.remediation_failed_result_digest == sha256_file(
        _repo() / "development_benchmark_breadth_remediation/results-v1/unblinded-result.json"
    )
    assert design.prior_results_preserved
    assert not design.external_validation_accessed
    assert design.provider_billed_calls == 0


def test_task_oracles_publish_a_basis_without_hidden_exact_vocabulary() -> None:
    design = load_breadth_instrument_design(_root())

    for wrapped in design.tasks:
        assert wrapped.task.held_out is False
        assert wrapped.stage == 3
        assert all(
            not check.exact_undisclosed_vocabulary_required for check in wrapped.oracle_checks
        )
        assert all(check.public_basis for check in wrapped.oracle_checks)
