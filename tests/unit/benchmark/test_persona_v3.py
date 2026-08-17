from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.automatic_runtime.models import (
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticNormStrength,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
)
from adaptation_compiler_lab.benchmark.persona_instrument import PersonaMaterialSource
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3ProfileClaim,
    PersonaV3ProfileOutput,
    PersonaV3ProfileSnapshot,
    PersonaV3Protocol,
    bind_v3_profile_material,
    bind_v3_profile_output,
    build_v3_profile_author_packet,
    build_v3_smoke_fixture,
    build_v3_smoke_oracle,
    persona_v3_profile_output_schema,
    persona_v3_schemas,
    score_v3_smoke_material,
)
from adaptation_compiler_lab.domain import ArtifactRoute
from adaptation_compiler_lab.serialization import canonical_json

ROOT = Path(__file__).resolve().parents[3]


def _features(*, workflow: bool = False) -> SemanticFeatureVector:
    return SemanticFeatureVector(
        assertion_kind=SemanticAssertionKind.NORMATIVE,
        norm_strength=SemanticNormStrength.PREFERENCE,
        workflow_structure=(
            SemanticWorkflowStructure.TRIGGERED_SEQUENCE
            if workflow
            else SemanticWorkflowStructure.NONE
        ),
        example_intent=SemanticExampleIntent.NONE,
        transition_intent=SemanticTransitionIntent.ADDITION,
    )


def _exact_profile() -> PersonaV3ProfileOutput:
    return PersonaV3ProfileOutput(
        snapshot=PersonaV3ProfileSnapshot(
            claims=(
                PersonaV3ProfileClaim(
                    statement="Lead River Station updates with the outcome, then the evidence.",
                    semantic_features=_features(),
                    source_turns=(2,),
                ),
                PersonaV3ProfileClaim(
                    statement=(
                        "During River Station production incidents, put immediate recovery "
                        "commands before the outcome summary."
                    ),
                    semantic_features=_features(workflow=True),
                    source_turns=(6,),
                ),
            )
        ),
        limitations=("Only the seven visible synthetic turns were considered.",),
    )


def test_v3_protocol_authorizes_only_one_non_evidentiary_smoke() -> None:
    protocol = PersonaV3Protocol()

    assert protocol.smoke_persona_count == 1
    assert protocol.smoke_session_maximum == 3
    assert protocol.full_grid_execution_authorized is False
    assert protocol.smoke_counts_toward_effectiveness_evidence is False
    assert protocol.provider_billed_calls == 0
    assert protocol.common_host_scope_registry is True
    assert protocol.model_authored_scope_has_delivery_authority is False
    assert protocol.model_authored_route_has_promotion_authority is False


def test_public_construction_packet_excludes_oracle_and_routing_authority() -> None:
    protocol = PersonaV3Protocol()
    fixture = build_v3_smoke_fixture()
    packet = build_v3_profile_author_packet(protocol, fixture)
    packet_text = canonical_json(packet)
    profile_schema = canonical_json(persona_v3_profile_output_schema())

    assert "oracle" not in packet_text.lower()
    assert "active_claims" not in packet_text
    assert "forbidden_source_turns" not in packet_text
    assert '"route"' not in profile_schema
    assert '"scope"' not in profile_schema
    assert fixture.case.persona_id == "sable"
    assert tuple(item.turn for item in fixture.evidence.messages) == tuple(range(1, 8))


def test_profile_route_and_scope_are_bound_only_by_trusted_code() -> None:
    fixture = build_v3_smoke_fixture()
    oracle = build_v3_smoke_oracle(fixture)
    material = bind_v3_profile_material(fixture=fixture, reviewed=_exact_profile())
    score = score_v3_smoke_material(fixture, oracle, material)

    assert material.source is PersonaMaterialSource.STATIC
    assert tuple(claim.route for claim in material.claims) == (
        ArtifactRoute.PREFERENCE,
        ArtifactRoute.PROCEDURE,
    )
    assert material.claims[0].scope == fixture.scope_registry.binding_for_turn(2).scope
    assert material.claims[1].scope == fixture.scope_registry.binding_for_turn(6).scope
    assert score.exact is True


def test_model_authored_route_scope_and_future_lineage_fail_closed() -> None:
    payload = _exact_profile().model_dump(mode="json", round_trip=True)
    payload["snapshot"]["claims"][0]["route"] = "preference"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        bind_v3_profile_output(json.dumps(payload))

    payload = _exact_profile().model_dump(mode="json", round_trip=True)
    payload["snapshot"]["claims"][0]["scope"] = {"project_ids": ["river-station"]}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        bind_v3_profile_output(json.dumps(payload))

    future = _exact_profile().model_copy(
        update={
            "snapshot": PersonaV3ProfileSnapshot(
                claims=(
                    PersonaV3ProfileClaim(
                        statement="Unsupported future behavior.",
                        semantic_features=_features(),
                        source_turns=(8,),
                    ),
                )
            )
        }
    )
    with pytest.raises(ValueError, match="hidden or future evidence"):
        bind_v3_profile_material(fixture=build_v3_smoke_fixture(), reviewed=future)


def test_separately_frozen_oracle_rejects_cross_case_scoring() -> None:
    fixture = build_v3_smoke_fixture()
    oracle = build_v3_smoke_oracle(fixture).model_copy(update={"case_id": "wrong-case"})
    material = bind_v3_profile_material(fixture=fixture, reviewed=_exact_profile())

    with pytest.raises(ValueError, match="crossed its public fixture"):
        score_v3_smoke_material(fixture, oracle, material)


def test_v3_schemas_are_closed_and_match_snapshots() -> None:
    schemas = persona_v3_schemas()

    assert len(schemas) == 7
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    for name, schema in schemas.items():
        snapshot = ROOT / "schemas" / "persona_evaluation" / "v3" / name
        assert json.loads(snapshot.read_text(encoding="utf-8")) == schema
