from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentPublicPlan,
    load_breadth_instrument_contract,
    load_breadth_instrument_design,
)
from adaptation_compiler_lab.benchmark.breadth_instrument_retry import (
    load_breadth_instrument_retry_contract,
    load_breadth_instrument_retry_design,
)


def _root() -> Path:
    return Path(__file__).parents[2] / "development_benchmark_breadth_instrument_repair"


def test_v3_retry_is_bound_to_failure_and_successful_smoke() -> None:
    base = load_breadth_instrument_design(_root())
    base_contract = load_breadth_instrument_contract(_root(), design=base)
    retry = load_breadth_instrument_retry_design(
        _root(),
        base_design=base,
        base_contract=base_contract,
    )
    contract = load_breadth_instrument_retry_contract(_root(), retry_design=retry)

    assert retry.failed_mapping_remains_withheld
    assert not retry.failed_grid_unblinded
    assert not retry.failed_grid_judged
    assert not retry.failed_targets_accessed_task_content
    assert retry.task_payloads_unchanged
    assert retry.condition_materials_unchanged
    assert retry.maximum_subscription_sessions == 9
    assert contract.target_model == "gpt-5.6-luna"
    assert contract.target_reasoning_effort == "medium"


def test_v3_retry_public_plan_remains_condition_blind() -> None:
    public_path = _root() / "RETRY_PUBLIC_PLAN-v1.json"
    public = BreadthInstrumentPublicPlan.model_validate_json(public_path.read_bytes())
    encoded = json.dumps(json.loads(public_path.read_text(encoding="utf-8")))

    assert len(public.run_order) == 8
    assert public.condition_mapping_withheld
    assert "compiled_adaptation" not in encoded
    assert "strong_static_profile" not in encoded


def test_v3_smoke_receipt_proves_edit_test_and_cleanup() -> None:
    receipt = json.loads((_root() / "RUNNER_SMOKE-v3.json").read_text(encoding="utf-8"))

    assert receipt["smoke_passed"] is True
    assert receipt["changed_only_registered_source"] is True
    assert receipt["tests_passed"] is True
    assert receipt["control_mountpoints_absent_before_scoring"] is True
    assert receipt["trace_conformant"] is True
    assert receipt["provider_billed_calls"] == 0
