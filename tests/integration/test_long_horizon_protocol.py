from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    LongHorizonPublicPlan,
    LongHorizonScenario,
    LongHorizonTurnKind,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file

ROOT = Path(__file__).parents[2]
BENCHMARK = ROOT / "development_benchmark_long_horizon"


def test_frozen_long_horizon_records_bind_exact_bytes() -> None:
    design_bytes = (BENCHMARK / "PREREGISTRATION-v1.json").read_bytes()
    public_bytes = (BENCHMARK / "PUBLIC_PLAN-v1.json").read_bytes()
    design = LongHorizonDesign.model_validate_json(design_bytes)
    scenario = LongHorizonScenario.model_validate_json(
        (BENCHMARK / "SCENARIO-v1.json").read_bytes()
    )
    public = LongHorizonPublicPlan.model_validate_json(public_bytes)

    assert (BENCHMARK / "PREREGISTRATION-v1.sha256").read_text().strip() == sha256_bytes(
        design_bytes
    )
    assert (BENCHMARK / "PUBLIC_PLAN-v1.sha256").read_text().strip() == sha256_bytes(public_bytes)
    assert design.scenario == scenario
    assert public.design_digest == design.content_digest
    assert public.scenario_digest == scenario.content_digest
    assert public.condition_mapping_withheld


def test_materials_share_evidence_and_match_frozen_6a4_sources() -> None:
    design = LongHorizonDesign.model_validate_json(
        (BENCHMARK / "PREREGISTRATION-v1.json").read_bytes()
    )
    bindings = json.loads((BENCHMARK / "MATERIAL_BINDINGS-v1.json").read_text())

    assert len({item.eligible_evidence_digest for item in design.materials}) == 1
    assert {item.eligible_evidence_digest for item in design.materials} == {
        bindings["eligible_evidence_digest"]
    }
    for material in design.materials:
        prefix = (
            "strong-profile" if material.condition.value == "strong_static_profile" else "compiled"
        )
        expected = tuple(
            (
                ROOT
                / "development_benchmark_breadth_replication"
                / "condition-materials"
                / f"{prefix}-stage-{stage}.md"
            ).read_text(encoding="utf-8").strip()
            for stage in (1, 2, 3)
        )
        assert material.stages == expected
        assert (
            list(material.stage_digests)
            == bindings["materials"][material.condition.value]["stage_digests"]
        )


def test_every_work_turn_binds_the_standalone_scorer() -> None:
    design = LongHorizonDesign.model_validate_json(
        (BENCHMARK / "PREREGISTRATION-v1.json").read_bytes()
    )
    scorer_digest = sha256_file(BENCHMARK / "independent_scorer.py")

    assert all(
        turn.task.scorer_digest == scorer_digest
        for turn in design.scenario.turns
        if turn.task.kind is not LongHorizonTurnKind.EXPLICIT_FEEDBACK
    )


def test_instrument_bindings_and_live_smoke_are_frozen() -> None:
    bindings = json.loads((BENCHMARK / "MATERIAL_BINDINGS-v1.json").read_text())
    instrument = bindings["instrument"]
    expected = {
        "conversation_runner_digest": sha256_file(
            ROOT / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation.py"
        ),
        "execution_coordinator_digest": sha256_file(
            ROOT / "scripts" / "run_long_horizon_comparison.py"
        ),
        "fixture_source_digest": sha256_file(
            ROOT / "src" / "adaptation_compiler_lab" / "benchmark" / "long_horizon_fixture.py"
        ),
        "scorer_digest": sha256_file(BENCHMARK / "independent_scorer.py"),
    }
    smoke = json.loads((BENCHMARK / "SMOKE_RECEIPT-v1.json").read_text())

    assert instrument == expected
    assert smoke["one_thread"]
    assert smoke["turns_conformant"]
    assert smoke["session_files_existed_during_smoke"]
    assert smoke["config_destroyed"]
    assert smoke["session_destroyed"]
    assert smoke["provider_billed_calls"] == 0
    assert not smoke["external_validation_accessed"]
