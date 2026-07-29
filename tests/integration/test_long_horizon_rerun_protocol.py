from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    LongHorizonPublicPlan,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file

ROOT = Path(__file__).parents[2]
BENCHMARK = ROOT / "development_benchmark_long_horizon"


def test_rerun_plan_preserves_design_scenario_and_materials() -> None:
    design = LongHorizonDesign.model_validate_json(
        (BENCHMARK / "PREREGISTRATION-v1.json").read_bytes()
    )
    public_bytes = (BENCHMARK / "PUBLIC_PLAN-v1.1.json").read_bytes()
    public = LongHorizonPublicPlan.model_validate_json(public_bytes)
    bindings = json.loads((BENCHMARK / "RERUN_BINDINGS-v1.1.json").read_text())

    assert (BENCHMARK / "PUBLIC_PLAN-v1.1.sha256").read_text().strip() == sha256_bytes(public_bytes)
    assert public.design_digest == design.content_digest
    assert public.scenario_digest == design.scenario.content_digest
    assert public.condition_mapping_withheld
    assert bindings["design_digest"] == design.content_digest
    assert bindings["public_plan_digest"] == public.content_digest
    assert bindings["unchanged_scenario_digest"] == design.scenario.content_digest
    assert bindings["unchanged_material_digests"] == {
        material.condition.value: list(material.stage_digests) for material in design.materials
    }


def test_rerun_binds_both_instruments_and_preserves_original_result() -> None:
    bindings = json.loads((BENCHMARK / "RERUN_BINDINGS-v1.1.json").read_text())
    instrument = bindings["instrument"]
    expected = {
        "conversation_runner_v1_digest": sha256_file(
            ROOT / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation.py"
        ),
        "conversation_runner_v2_digest": sha256_file(
            ROOT / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation_v2.py"
        ),
        "original_coordinator_digest": sha256_file(
            ROOT / "scripts" / "run_long_horizon_comparison.py"
        ),
        "rerun_coordinator_digest": sha256_file(
            ROOT / "scripts" / "run_long_horizon_comparison_v2.py"
        ),
        "scorer_digest": sha256_file(BENCHMARK / "independent_scorer.py"),
    }

    assert instrument == expected
    assert bindings["original_blind_report_digest"] == sha256_file(
        BENCHMARK / "results-v1" / "BLIND_REPORT-v1.json"
    )
    assert bindings["condition_mapping_withheld"]
    assert bindings["provider_billed_calls"] == 0
    assert not bindings["external_validation_accessed"]
