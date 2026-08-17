from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.models import (
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticNormStrength,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
)
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3ProfileClaim,
    PersonaV3ProfileOutput,
    PersonaV3ProfileSnapshot,
)
from adaptation_compiler_lab.benchmark.persona_v31 import (
    PersonaV31Protocol,
    PersonaV31Report,
    PersonaV31SensorResult,
    bind_v31_profile_material,
    build_v31_author_packet,
    build_v31_fixture,
    build_v31_oracle,
    persona_v31_schemas,
    score_v31_material,
)
from adaptation_compiler_lab.domain import ArtifactRoute
from adaptation_compiler_lab.serialization import canonical_json

ROOT = Path(__file__).resolve().parents[3]


def test_v31_fixture_removes_v3_route_and_lifecycle_confounds() -> None:
    fixture = build_v31_fixture()
    messages = {item.turn: item.message for item in fixture.evidence.messages}

    assert "prefer plain, literal language" in messages[2]
    assert "then recent deploys, then queue depth" in messages[6]
    assert "exception" not in messages[6].casefold()
    assert "correction" not in messages[6].casefold()
    assert fixture.case.persona_id == "nola"
    assert fixture.case.current_scope.activation_conditions == ("production_incident",)


def test_v31_static_exact_state_uses_deterministic_route_and_host_scope() -> None:
    fixture = build_v31_fixture()
    profile = PersonaV3ProfileOutput(
        snapshot=PersonaV3ProfileSnapshot(
            claims=(
                PersonaV3ProfileClaim(
                    statement="Use plain, literal language for Copper Finch work.",
                    semantic_features=SemanticFeatureVector(
                        assertion_kind=SemanticAssertionKind.NORMATIVE,
                        norm_strength=SemanticNormStrength.PREFERENCE,
                        workflow_structure=SemanticWorkflowStructure.NONE,
                        example_intent=SemanticExampleIntent.NONE,
                        transition_intent=SemanticTransitionIntent.ADDITION,
                    ),
                    source_turns=(2,),
                ),
                PersonaV3ProfileClaim(
                    statement=(
                        "During Copper Finch incidents, check service health, recent deploys, "
                        "then queue depth."
                    ),
                    semantic_features=SemanticFeatureVector(
                        assertion_kind=SemanticAssertionKind.NORMATIVE,
                        norm_strength=SemanticNormStrength.INVARIANT,
                        workflow_structure=SemanticWorkflowStructure.TRIGGERED_SEQUENCE,
                        example_intent=SemanticExampleIntent.NONE,
                        transition_intent=SemanticTransitionIntent.ADDITION,
                    ),
                    source_turns=(6,),
                ),
            )
        ),
        limitations=("Only the seven visible synthetic turns were considered.",),
    )
    material = bind_v31_profile_material(fixture=fixture, reviewed=profile)
    score = score_v31_material(fixture, build_v31_oracle(fixture), material)

    assert score.exact is True
    assert tuple(item.route for item in material.claims) == (
        ArtifactRoute.PREFERENCE,
        ArtifactRoute.PROCEDURE,
    )


def test_v31_construction_packet_excludes_oracle_and_full_grid_remains_blocked() -> None:
    protocol = PersonaV31Protocol()
    packet = build_v31_author_packet(protocol, build_v31_fixture())
    rendered = canonical_json(packet)

    assert "oracle" not in rendered.casefold()
    assert "active_claims" not in rendered
    assert protocol.full_grid_execution_authorized is False
    assert protocol.counts_toward_effectiveness_evidence is False
    assert protocol.session_maximum == 3


def test_v31_schemas_match_closed_snapshots() -> None:
    schemas = persona_v31_schemas()

    assert len(schemas) == 6
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    for name, schema in schemas.items():
        snapshot = ROOT / "schemas" / "persona_evaluation" / "v3.1" / name
        assert json.loads(snapshot.read_text(encoding="utf-8")) == schema


def test_v31_frozen_result_preserves_static_pass_and_compiled_failure() -> None:
    result_root = ROOT / "development_benchmark_persona_v31" / "results"
    sensor = PersonaV31SensorResult.model_validate_json(
        (result_root / "SMOKE-SENSOR-RESULT-v1.json").read_bytes()
    )
    report = PersonaV31Report.model_validate_json(
        (result_root / "SMOKE-REPORT-v1.json").read_bytes()
    )

    assert report.passed is False
    assert report.full_grid_launch_gate_passed is False
    assert report.static_score.exact is True
    assert report.compiled_score.missing_source_turns == (6,)
    assert report.compiled_score.route_mismatch_source_turns == (2,)
    assert sensor.records[1].route is ArtifactRoute.EXAMPLE
    assert sensor.records[1].approved is True
    assert sensor.records[5].approved is False
    assert report.provider_billed_calls == 0
    assert report.counts_toward_effectiveness_evidence is False
