from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.persona_v3 import PersonaV3ProfileOutput
from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32ConstructionReport,
    PersonaV32Freeze,
    PersonaV32Oracle,
    PersonaV32Protocol,
    build_v32_fixture,
    score_v32_material,
)
from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    build_v32_construction_adjudication,
    persona_v32_adjudication_schemas,
)
from adaptation_compiler_lab.domain import ArtifactRoute
from adaptation_compiler_lab.serialization import canonical_digest

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "development_benchmark_persona_v32"


def _adjudication() -> tuple[PersonaV32Oracle, object]:
    protocol = PersonaV32Protocol.model_validate_json(
        (BENCHMARK / "PROTOCOL-v3.2.json").read_bytes()
    )
    freeze = PersonaV32Freeze.model_validate_json((BENCHMARK / "FREEZE-v1.json").read_bytes())
    oracle = PersonaV32Oracle.model_validate_json((BENCHMARK / "ORACLE-v1.json").read_bytes())
    report = PersonaV32ConstructionReport.model_validate_json(
        (BENCHMARK / "construction-results-v1/CONSTRUCTION-REPORT-v1.json").read_bytes()
    )
    reviewed = PersonaV3ProfileOutput.model_validate_json(
        (BENCHMARK / "construction-results-v1/PROFILE-REVIEWED-v1.json").read_bytes()
    )
    return build_v32_construction_adjudication(
        original_protocol_digest=canonical_digest(protocol),
        original_freeze_digest=canonical_digest(freeze),
        original_oracle=oracle,
        report=report,
        reviewed=reviewed,
        route_policy_source_digest="sha256:" + "0" * 64,
    )


def test_v32_adjudication_preserves_failed_result_and_changes_only_material_route() -> None:
    original = PersonaV32Oracle.model_validate_json((BENCHMARK / "ORACLE-v1.json").read_bytes())
    corrected, adjudication = _adjudication()

    assert original.material.active_claims[0].route is ArtifactRoute.PREFERENCE
    assert corrected.material.active_claims[0].route is ArtifactRoute.PROCEDURE
    assert original.material.active_claims[1:] == corrected.material.active_claims[1:]
    assert original.tasks == corrected.tasks
    assert adjudication.task_oracles_unchanged is True
    assert adjudication.target_material_bytes_unchanged is True
    assert adjudication.adjudication_sessions == 0


def test_v32_corrected_oracle_scores_both_preserved_materials_exactly() -> None:
    corrected, _ = _adjudication()
    report = PersonaV32ConstructionReport.model_validate_json(
        (BENCHMARK / "construction-results-v1/CONSTRUCTION-REPORT-v1.json").read_bytes()
    )
    fixture = build_v32_fixture()

    assert report.exact_target_gate_passed is False
    assert score_v32_material(fixture, corrected, report.compiled_material).exact is True
    assert score_v32_material(fixture, corrected, report.static_material).exact is True


def test_v32_adjudication_schemas_match_snapshots() -> None:
    for name, schema in persona_v32_adjudication_schemas().items():
        snapshot = ROOT / "schemas" / "persona_evaluation" / "v3.2" / name
        assert json.loads(snapshot.read_text(encoding="utf-8")) == schema
