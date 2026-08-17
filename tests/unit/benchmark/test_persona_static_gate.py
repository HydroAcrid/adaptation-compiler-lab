from __future__ import annotations

import json
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.persona_calibration import (
    build_calibration_history,
    build_calibration_profile,
)
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaMaterialSnapshot,
    PersonaMaterialSource,
    build_stage_evidence,
    render_neutral_guidance,
)
from adaptation_compiler_lab.benchmark.persona_static_gate import (
    PersonaHostScopeBinding,
    PersonaHostScopeRegistry,
    PersonaTransitionExpectation,
    PersonaTransitionKind,
    audit_revealed_v21_scope_transport,
    behavior_proposals,
    bind_host_scoped_claims,
    build_transition_scorecard,
    persona_static_gate_schemas,
    run_pre_v3_static_gate,
    score_transition,
)
from adaptation_compiler_lab.domain import Scope

ROOT = Path(__file__).resolve().parents[3]
DIGEST = "sha256:" + "a" * 64


def _scope(*, incident: bool = False) -> Scope:
    return Scope(
        subject_ids=("calibration-user",),
        project_ids=("lantern-docs",),
        activation_conditions=(("incident",) if incident else ()),
    )


def _material(case_id: str, turns: tuple[int, ...]) -> PersonaMaterialSnapshot:
    profile = build_calibration_profile(3)
    all_claims = bind_host_scoped_claims(
        evidence=build_stage_evidence(build_calibration_history(), 3),
        proposals=behavior_proposals(profile),
        registry=PersonaHostScopeRegistry(
            persona_id="calibration-alex",
            stage=3,
            bindings=(
                PersonaHostScopeBinding(
                    binding_id="scope-turn-6",
                    source_turn=6,
                    scope=_scope(incident=True),
                ),
                PersonaHostScopeBinding(
                    binding_id="scope-turn-10",
                    source_turn=10,
                    scope=_scope(),
                ),
            ),
        ),
    )
    selected = tuple(claim for claim in all_claims if claim.source_turns[-1] in turns)
    return PersonaMaterialSnapshot(
        case_id=case_id,
        persona_id="calibration-alex",
        source=PersonaMaterialSource.STATIC,
        claims=selected,
        target_guidance=render_neutral_guidance(selected),
        evidence_checkpoint_digest=DIGEST,
        independently_reviewed=True,
    )


def test_revealed_v21_scope_transport_binds_every_reviewed_claim() -> None:
    audit = audit_revealed_v21_scope_transport(ROOT)

    assert audit.reviewed_snapshots == 24
    assert audit.reviewed_claims == 39
    assert audit.host_bound_claims == 39
    assert audit.applicable_projected_claims > 0
    assert audit.fuzzy_scope_matches == 0
    assert audit.hidden_oracle_accessed is False
    assert audit.complete is True


def test_host_scope_binding_ignores_model_scope_and_rejects_unknown_turn() -> None:
    reviewed = build_calibration_profile(1)
    proposals = behavior_proposals(reviewed)
    registry = PersonaHostScopeRegistry(
        persona_id="calibration-alex",
        stage=1,
        bindings=(
            PersonaHostScopeBinding(
                binding_id="scope-turn-2",
                source_turn=2,
                scope=_scope(),
            ),
        ),
    )
    bound = bind_host_scoped_claims(
        evidence=build_stage_evidence(build_calibration_history(), 1),
        proposals=proposals,
        registry=registry,
    )
    assert bound[0].scope == _scope()

    missing = registry.model_copy(
        update={
            "bindings": (
                PersonaHostScopeBinding(
                    binding_id="scope-turn-1",
                    source_turn=1,
                    scope=_scope(),
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="no trusted scope binding"):
        bind_host_scoped_claims(
            evidence=build_stage_evidence(build_calibration_history(), 1),
            proposals=proposals,
            registry=missing,
        )


def test_revocation_scoring_is_non_vacuous() -> None:
    expectation = PersonaTransitionExpectation(
        transition_id="revocation",
        kind=PersonaTransitionKind.REVOCATION,
        prior_case_id="before",
        current_case_id="after",
        prior_active_source_turns=(10,),
        current_active_source_turns=(),
    )
    valid = score_transition(
        expectation=expectation,
        prior=_material("before", (10,)),
        current=_material("after", ()),
    )
    vacuous = score_transition(
        expectation=expectation,
        prior=_material("before", ()),
        current=_material("after", ()),
    )

    assert valid.exact is True
    assert valid.removal_requirement_satisfied is True
    assert vacuous.exact is False
    assert vacuous.prior_state_exact is False
    assert vacuous.removal_requirement_satisfied is False


def test_transition_scorecard_reports_kinds_separately() -> None:
    addition = PersonaTransitionExpectation(
        transition_id="01-addition",
        kind=PersonaTransitionKind.ADDITION,
        prior_case_id="empty",
        current_case_id="active",
        prior_active_source_turns=(),
        current_active_source_turns=(10,),
    )
    revocation = PersonaTransitionExpectation(
        transition_id="02-revocation",
        kind=PersonaTransitionKind.REVOCATION,
        prior_case_id="active",
        current_case_id="empty-again",
        prior_active_source_turns=(10,),
        current_active_source_turns=(),
    )
    scores = (
        score_transition(
            expectation=addition,
            prior=_material("empty", ()),
            current=_material("active", (10,)),
        ),
        score_transition(
            expectation=revocation,
            prior=_material("active", (10,)),
            current=_material("empty-again", ()),
        ),
    )

    scorecard = build_transition_scorecard(scores)
    assert scorecard.exact is True
    assert [(item.kind.value, item.exact, item.total) for item in scorecard.slices] == [
        ("addition", 1, 1),
        ("revocation", 1, 1),
    ]


def test_pre_v3_static_gate_is_non_evidentiary_and_zero_session() -> None:
    report = run_pre_v3_static_gate(ROOT)

    assert report.passed is True
    assert report.language_understanding_evaluated is False
    assert report.counts_toward_effectiveness_evidence is False
    assert report.agent_sessions == 0
    assert report.provider_billed_calls == 0
    assert len(report.transition_scorecard.slices) == 5
    snapshot = (
        ROOT / "development_benchmark_persona_static_gate" / "PRE-V3-STATIC-GATE-REPORT-v1.json"
    )
    assert json.loads(snapshot.read_text(encoding="utf-8")) == report.model_dump(mode="json")

    tampered = report.model_dump(mode="json")
    tampered["checks"] = tampered["checks"][:-1]
    with pytest.raises(ValueError, match="check set is incomplete"):
        type(report).model_validate_json(json.dumps(tampered))


def test_static_gate_schemas_are_closed() -> None:
    schemas = persona_static_gate_schemas()

    assert set(schemas) == {
        "persona_host_scope_registry.schema.json",
        "persona_pre_v3_static_gate_report.schema.json",
        "persona_transition_expectation.schema.json",
    }
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    for name, schema in schemas.items():
        snapshot = ROOT / "schemas" / "persona_static_gate" / "v1" / name
        assert json.loads(snapshot.read_text(encoding="utf-8")) == schema
