"""Deterministic pre-v3 engineering gate for persona scope and lifecycle mechanics.

This module deliberately does not evaluate natural-language understanding. It verifies the
host-owned mechanics that must be correct before another model-facing persona evaluation is worth
running: exact scope transport, applicability, lifecycle transitions, and non-vacuous scoring.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticNormStrength,
    SemanticRouteResolution,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
)
from adaptation_compiler_lab.automatic_runtime.semantic_routing import route_semantic_features
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaMaterialClaim,
    PersonaMaterialSnapshot,
    PersonaMaterialSource,
    PersonaModelProfileOutput,
    PersonaPublicCase,
    PersonaSensorRecord,
    PersonaStageEvidence,
    PersonaV21SensorBatch,
    compile_sensor_material,
    render_neutral_guidance,
)
from adaptation_compiler_lab.domain import (
    ArtifactRoute,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Scope,
    scope_is_within,
)
from adaptation_compiler_lab.serialization import canonical_digest

_STATIC_GATE_CHECKS = tuple(
    sorted(
        {
            "ambiguous semantic meaning remains review-required",
            "compiled and static lanes consume one host-owned scope vocabulary",
            "compiled scope substitution fails closed",
            "lifecycle results are reported in separate transition slices",
            "neutral contexts remain inactive",
            "preference-only meaning uses the least-invasive preference route",
            "revealed v2.1 reviewed claims bind without fuzzy scope matching",
            "revocation requires a previously recovered active behavior",
            "scoped exceptions activate only in their registered context",
        }
    )
)


class PersonaHostScopeBinding(FrozenModel):
    """Trusted host mapping from one evidence turn to one exact registered scope."""

    binding_id: Identifier
    source_turn: Annotated[int, Field(ge=1, le=15)]
    scope: Scope


class PersonaHostScopeRegistry(FrozenModel):
    """The canonical scope vocabulary shared by both comparison lanes."""

    registry_version: Literal["1.0.0"] = "1.0.0"
    persona_id: Identifier
    stage: Annotated[int, Field(ge=1, le=4)]
    bindings: Annotated[tuple[PersonaHostScopeBinding, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def bindings_are_exact(self) -> Self:
        turns = tuple(item.source_turn for item in self.bindings)
        identifiers = tuple(item.binding_id for item in self.bindings)
        if turns != tuple(sorted(set(turns))):
            raise ValueError("scope bindings must be ordered and unique by source turn")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("scope binding IDs must be unique")
        return self

    def binding_for_turn(self, source_turn: int) -> PersonaHostScopeBinding:
        """Resolve one exact binding without fuzzy matching or model-authored identifiers."""

        for binding in self.bindings:
            if binding.source_turn == source_turn:
                return binding
        raise ValueError(f"source turn {source_turn} has no trusted scope binding")


class PersonaBehaviorClaimProposal(FrozenModel):
    """Transport-only content retained from a reviewer after discarding authored scope.

    The route remains an audited comparator proposal. Product promotion still recomputes routing
    from semantic features through deterministic least-invasive policy.
    """

    statement: NonEmptyStr
    route: ArtifactRoute
    source_turns: Annotated[tuple[int, ...], Field(min_length=1, max_length=4)]

    @field_validator("source_turns")
    @classmethod
    def turns_are_sorted_unique(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("behavior proposal turns must be sorted and unique")
        return value


class PersonaScopeTransportAudit(FrozenModel):
    """Raw-free audit of the revealed v2.1 static comparator transport defect."""

    audit_version: Literal["1.0.0"] = "1.0.0"
    reviewed_snapshots: int = Field(ge=1)
    reviewed_claims: int = Field(ge=1)
    host_bound_claims: int = Field(ge=0)
    applicable_projected_claims: int = Field(ge=0)
    fuzzy_scope_matches: Literal[0] = 0
    hidden_oracle_accessed: Literal[False] = False

    @property
    def complete(self) -> bool:
        return self.reviewed_claims == self.host_bound_claims


class PersonaTransitionKind(StrEnum):
    ADDITION = "addition"
    SCOPED_EXCEPTION = "scoped_exception"
    CORRECTION = "correction"
    SUPERSESSION = "supersession"
    REVOCATION = "revocation"
    NEUTRAL = "neutral"


class PersonaTransitionExpectation(FrozenModel):
    """Exact before/after state required to award lifecycle credit."""

    transition_id: Identifier
    kind: PersonaTransitionKind
    prior_case_id: Identifier
    current_case_id: Identifier
    prior_active_source_turns: tuple[int, ...]
    current_active_source_turns: tuple[int, ...]

    @field_validator("prior_active_source_turns", "current_active_source_turns")
    @classmethod
    def active_turns_are_sorted_unique(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("transition active turns must be sorted and unique")
        return value

    @model_validator(mode="after")
    def transition_has_required_shape(self) -> Self:
        prior = set(self.prior_active_source_turns)
        current = set(self.current_active_source_turns)
        added = current - prior
        removed = prior - current
        if self.kind in {PersonaTransitionKind.ADDITION, PersonaTransitionKind.SCOPED_EXCEPTION}:
            if not added or removed:
                raise ValueError("addition and exception transitions must only add active claims")
        elif self.kind in {
            PersonaTransitionKind.CORRECTION,
            PersonaTransitionKind.SUPERSESSION,
        }:
            if not added or not removed:
                raise ValueError("correction and supersession require an addition and a removal")
        elif self.kind is PersonaTransitionKind.REVOCATION:
            if not removed or added:
                raise ValueError("revocation must remove at least one previously active claim")
        elif prior != current:
            raise ValueError("neutral transitions must preserve the exact active state")
        return self


class PersonaTransitionScore(FrozenModel):
    transition_id: Identifier
    kind: PersonaTransitionKind
    prior_state_exact: bool
    current_state_exact: bool
    addition_requirement_satisfied: bool
    removal_requirement_satisfied: bool
    exact: bool

    @model_validator(mode="after")
    def exact_matches_components(self) -> Self:
        expected = all(
            (
                self.prior_state_exact,
                self.current_state_exact,
                self.addition_requirement_satisfied,
                self.removal_requirement_satisfied,
            )
        )
        if self.exact is not expected:
            raise ValueError("transition exact flag does not match its components")
        return self


class PersonaTransitionSlice(FrozenModel):
    kind: PersonaTransitionKind
    total: int = Field(ge=1)
    exact: int = Field(ge=0)

    @model_validator(mode="after")
    def exact_does_not_exceed_total(self) -> Self:
        if self.exact > self.total:
            raise ValueError("exact transition count cannot exceed total")
        return self


class PersonaTransitionScorecard(FrozenModel):
    scores: tuple[PersonaTransitionScore, ...]
    slices: tuple[PersonaTransitionSlice, ...]
    exact: bool

    @model_validator(mode="after")
    def aggregation_is_exact(self) -> Self:
        identifiers = tuple(item.transition_id for item in self.scores)
        if identifiers != tuple(sorted(set(identifiers))):
            raise ValueError("transition scores must be ordered and unique")
        expected_slices = tuple(
            PersonaTransitionSlice(
                kind=kind,
                total=sum(item.kind is kind for item in self.scores),
                exact=sum(item.kind is kind and item.exact for item in self.scores),
            )
            for kind in PersonaTransitionKind
            if any(item.kind is kind for item in self.scores)
        )
        if self.slices != expected_slices:
            raise ValueError("transition slices do not match their exact scores")
        expected_exact = bool(self.scores) and all(item.exact for item in self.scores)
        if self.exact is not expected_exact:
            raise ValueError("transition scorecard exact flag does not match its scores")
        return self


class PersonaPreV3StaticGateReport(FrozenModel):
    """Evidence that compiler mechanics are ready for a separate AI effectiveness test."""

    report_version: Literal["1.0.0"] = "1.0.0"
    gate_id: Literal["temper-pre-v3-static-engineering"] = "temper-pre-v3-static-engineering"
    checks: tuple[NonEmptyStr, ...]
    scope_transport: PersonaScopeTransportAudit
    transition_scorecard: PersonaTransitionScorecard
    language_understanding_evaluated: Literal[False] = False
    counts_toward_effectiveness_evidence: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    agent_sessions: Literal[0] = 0
    passed: bool

    @model_validator(mode="after")
    def gate_is_fail_closed(self) -> Self:
        if self.checks != _STATIC_GATE_CHECKS:
            raise ValueError("static gate check set is incomplete or noncanonical")
        required_kinds = {
            PersonaTransitionKind.ADDITION,
            PersonaTransitionKind.SCOPED_EXCEPTION,
            PersonaTransitionKind.CORRECTION,
            PersonaTransitionKind.REVOCATION,
            PersonaTransitionKind.NEUTRAL,
        }
        observed_kinds = {item.kind for item in self.transition_scorecard.scores}
        transport_exact = (
            self.scope_transport.reviewed_snapshots == 24
            and self.scope_transport.reviewed_claims == 39
            and self.scope_transport.host_bound_claims == 39
            and self.scope_transport.applicable_projected_claims > 0
        )
        expected = (
            transport_exact and observed_kinds == required_kinds and self.transition_scorecard.exact
        )
        if self.passed is not expected:
            raise ValueError("static gate pass flag does not match deterministic evidence")
        return self


def behavior_proposals(
    reviewed: PersonaModelProfileOutput,
) -> tuple[PersonaBehaviorClaimProposal, ...]:
    """Keep behavioral semantics and lineage while dropping untrusted scope vocabulary."""

    return tuple(
        PersonaBehaviorClaimProposal(
            statement=claim.statement,
            route=claim.route,
            source_turns=claim.source_turns,
        )
        for claim in reviewed.snapshot.claims
    )


def build_revealed_v21_host_scope_registry(
    *,
    persona_id: Identifier,
    stage: int,
    batches: tuple[PersonaV21SensorBatch, ...],
) -> PersonaHostScopeRegistry:
    """Reconstruct v2.1 bindings from trusted host batches, never from model prose."""

    if stage not in range(1, 5):
        raise ValueError("scope registry stage must be between one and four")
    bindings: list[PersonaHostScopeBinding] = []
    for batch in sorted(batches, key=lambda item: item.stage):
        if batch.persona_id != persona_id:
            raise ValueError("scope registry crossed personas")
        if batch.stage > min(stage, 3):
            continue
        bindings.extend(
            PersonaHostScopeBinding(
                binding_id=f"scope-{persona_id}-turn-{message.turn}",
                source_turn=message.turn,
                scope=batch.scope,
            )
            for message in batch.messages
        )
    if not bindings:
        raise ValueError("scope registry has no visible host bindings")
    return PersonaHostScopeRegistry(
        persona_id=persona_id,
        stage=stage,
        bindings=tuple(sorted(bindings, key=lambda item: item.source_turn)),
    )


def bind_host_scoped_claims(
    *,
    evidence: PersonaStageEvidence,
    proposals: tuple[PersonaBehaviorClaimProposal, ...],
    registry: PersonaHostScopeRegistry,
) -> tuple[PersonaMaterialClaim, ...]:
    """Bind reviewed behavior to the latest cited turn's exact host-owned scope."""

    if evidence.persona_id != registry.persona_id or evidence.stage != registry.stage:
        raise ValueError("host scope binding crossed persona or stage")
    visible = {item.turn: item for item in evidence.messages}
    claims: list[PersonaMaterialClaim] = []
    for proposal in proposals:
        if any(turn not in visible for turn in proposal.source_turns):
            raise ValueError("behavior proposal cited hidden or future evidence")
        governing = registry.binding_for_turn(proposal.source_turns[-1])
        claim_digest = canonical_digest(
            {
                "persona_id": evidence.persona_id,
                "proposal": proposal.model_dump(mode="json", round_trip=True),
                "scope_binding_id": governing.binding_id,
            }
        ).removeprefix("sha256:")
        claims.append(
            PersonaMaterialClaim(
                claim_id=f"claim-{claim_digest[:24]}",
                statement=proposal.statement,
                route=proposal.route,
                scope=governing.scope,
                source_turns=proposal.source_turns,
                evidence_digests=tuple(
                    canonical_digest(visible[turn]) for turn in proposal.source_turns
                ),
            )
        )
    return tuple(claims)


def bind_host_scoped_profile_material(
    *,
    case: PersonaPublicCase,
    evidence: PersonaStageEvidence,
    reviewed: PersonaModelProfileOutput,
    registry: PersonaHostScopeRegistry,
) -> PersonaMaterialSnapshot:
    """Project a reviewed profile using only host-owned scope applicability."""

    if case.persona_id != evidence.persona_id or case.stage != evidence.stage:
        raise ValueError("profile material crossed persona or stage")
    if reviewed.snapshot.stage != case.stage:
        raise ValueError("reviewed profile output crossed stages")
    bound = bind_host_scoped_claims(
        evidence=evidence,
        proposals=behavior_proposals(reviewed),
        registry=registry,
    )
    applicable = tuple(item for item in bound if scope_is_within(case.current_scope, item.scope))
    return PersonaMaterialSnapshot(
        snapshot_version="2.1.0",
        case_id=case.case_id,
        persona_id=case.persona_id,
        source=PersonaMaterialSource.STATIC,
        claims=applicable,
        target_guidance=render_neutral_guidance(applicable),
        evidence_checkpoint_digest=evidence.content_digest,
        independently_reviewed=True,
    )


def compile_host_scoped_sensor_material(
    *,
    case: PersonaPublicCase,
    evidence: PersonaStageEvidence,
    records: tuple[PersonaSensorRecord, ...],
    registry: PersonaHostScopeRegistry,
) -> PersonaMaterialSnapshot:
    """Require compiled proposals to use the same exact scope vocabulary as profiles."""

    if registry.persona_id != case.persona_id or registry.stage != case.stage:
        raise ValueError("compiled scope registry crossed persona or stage")
    for record in records:
        if registry.binding_for_turn(record.turn).scope != record.scope:
            raise ValueError("sensor record substituted a noncanonical scope")
    return compile_sensor_material(case=case, evidence=evidence, records=records)


def _active_turns(material: PersonaMaterialSnapshot) -> tuple[int, ...]:
    return tuple(sorted(claim.source_turns[-1] for claim in material.claims))


def score_transition(
    *,
    expectation: PersonaTransitionExpectation,
    prior: PersonaMaterialSnapshot,
    current: PersonaMaterialSnapshot,
) -> PersonaTransitionScore:
    """Award lifecycle credit only when the required before-state was actually recovered."""

    if prior.case_id != expectation.prior_case_id or current.case_id != expectation.current_case_id:
        raise ValueError("transition score crossed its registered case binding")
    if prior.persona_id != current.persona_id or prior.source is not current.source:
        raise ValueError("transition score crossed persona or material source")
    actual_prior = set(_active_turns(prior))
    actual_current = set(_active_turns(current))
    expected_prior = set(expectation.prior_active_source_turns)
    expected_current = set(expectation.current_active_source_turns)
    required_added = expected_current - expected_prior
    required_removed = expected_prior - expected_current
    prior_exact = actual_prior == expected_prior
    current_exact = actual_current == expected_current
    addition_satisfied = required_added <= actual_current and not (required_added & actual_prior)
    removal_satisfied = required_removed <= actual_prior and not (required_removed & actual_current)
    exact = prior_exact and current_exact and addition_satisfied and removal_satisfied
    return PersonaTransitionScore(
        transition_id=expectation.transition_id,
        kind=expectation.kind,
        prior_state_exact=prior_exact,
        current_state_exact=current_exact,
        addition_requirement_satisfied=addition_satisfied,
        removal_requirement_satisfied=removal_satisfied,
        exact=exact,
    )


def build_transition_scorecard(
    scores: tuple[PersonaTransitionScore, ...],
) -> PersonaTransitionScorecard:
    if not scores:
        raise ValueError("transition scorecard requires at least one score")
    if tuple(item.transition_id for item in scores) != tuple(
        sorted({item.transition_id for item in scores})
    ):
        raise ValueError("transition scores must be ordered and unique")
    slices = tuple(
        PersonaTransitionSlice(
            kind=kind,
            total=sum(item.kind is kind for item in scores),
            exact=sum(item.kind is kind and item.exact for item in scores),
        )
        for kind in PersonaTransitionKind
        if any(item.kind is kind for item in scores)
    )
    return PersonaTransitionScorecard(
        scores=scores,
        slices=slices,
        exact=all(item.exact for item in scores),
    )


def audit_revealed_v21_scope_transport(root: Path) -> PersonaScopeTransportAudit:
    """Rebind all revealed reviewed claims from public host metadata only."""

    benchmark_root = root / "development_benchmark_persona_v21"
    reviewed_paths = sorted((benchmark_root / "profile-results").glob("*-stage-*.reviewed.json"))
    if len(reviewed_paths) != 24:
        raise ValueError("revealed v2.1 scope audit requires exactly 24 reviewed snapshots")
    reviewed_claims = 0
    host_bound_claims = 0
    applicable_claims = 0
    for path in reviewed_paths:
        stem = path.name.removesuffix(".reviewed.json")
        persona_id, _, stage_text = stem.partition("-stage-")
        stage = int(stage_text)
        public_payload = json.loads(
            (benchmark_root / "public-cases" / f"{persona_id}-v21-stage-{stage}.json").read_text()
        )
        case = PersonaPublicCase.model_validate_json(
            json.dumps(public_payload["case"]), strict=True
        )
        evidence = PersonaStageEvidence.model_validate_json(
            json.dumps(public_payload["evidence"]), strict=True
        )
        reviewed = PersonaModelProfileOutput.model_validate_json(path.read_text(), strict=True)
        batches = tuple(
            PersonaV21SensorBatch.model_validate_json(batch.read_text(), strict=True)
            for batch in sorted(
                (benchmark_root / "sensor-batches").glob(f"sensor-{persona_id}-stage-*.json")
            )
        )
        registry = build_revealed_v21_host_scope_registry(
            persona_id=persona_id,
            stage=stage,
            batches=batches,
        )
        proposals = behavior_proposals(reviewed)
        bound = bind_host_scoped_claims(evidence=evidence, proposals=proposals, registry=registry)
        material = bind_host_scoped_profile_material(
            case=case,
            evidence=evidence,
            reviewed=reviewed,
            registry=registry,
        )
        reviewed_claims += len(proposals)
        host_bound_claims += len(bound)
        applicable_claims += len(material.claims)
    return PersonaScopeTransportAudit(
        reviewed_snapshots=len(reviewed_paths),
        reviewed_claims=reviewed_claims,
        host_bound_claims=host_bound_claims,
        applicable_projected_claims=applicable_claims,
    )


def _empty_like(material: PersonaMaterialSnapshot, *, case_id: str) -> PersonaMaterialSnapshot:
    return material.model_copy(
        update={
            "case_id": case_id,
            "claims": (),
            "target_guidance": render_neutral_guidance(()),
        }
    )


def run_pre_v3_static_gate(root: Path) -> PersonaPreV3StaticGateReport:
    """Run the zero-session engineering gate against public and disposable fixtures."""

    from adaptation_compiler_lab.benchmark.persona_calibration import (
        build_calibration_history,
        build_calibration_sensor_records,
    )
    from adaptation_compiler_lab.benchmark.persona_instrument import build_stage_evidence

    scope_audit = audit_revealed_v21_scope_transport(root)
    history = build_calibration_history()
    records = build_calibration_sensor_records()
    broad_scope = records[0].scope
    exception_scope = records[1].scope

    def case(stage: int, *, incident: bool = False, unrelated: bool = False) -> PersonaPublicCase:
        checkpoint = (3, 7, 11, 15)[stage - 1]
        selected_scope = exception_scope if incident else broad_scope
        if unrelated:
            selected_scope = selected_scope.model_copy(update={"project_ids": ("other-project",)})
        context_kind = "unrelated" if unrelated else "incident" if incident else "normal"
        return PersonaPublicCase.model_validate(
            {
                "case_id": f"static-gate-stage-{stage}-{context_kind}",
                "persona_id": history.persona_id,
                "stage": stage,
                "checkpoint_turn": checkpoint,
                "current_scope": selected_scope,
                "context_label": "disposable-static-gate",
                "scenario": "Exercise deterministic scope and lifecycle mechanics.",
            }
        )

    def registry(stage: int) -> PersonaHostScopeRegistry:
        visible_turn = (3, 7, 11, 15)[stage - 1]
        bindings = tuple(
            PersonaHostScopeBinding(
                binding_id=f"calibration-scope-turn-{record.turn}",
                source_turn=record.turn,
                scope=record.scope,
            )
            for record in records
            if record.turn <= visible_turn
        )
        return PersonaHostScopeRegistry(
            persona_id=history.persona_id,
            stage=stage,
            bindings=bindings,
        )

    def compiled(
        stage: int, *, incident: bool = False, unrelated: bool = False
    ) -> PersonaMaterialSnapshot:
        evidence = build_stage_evidence(history, stage)
        visible = tuple(record for record in records if record.turn <= evidence.checkpoint_turn)
        return compile_host_scoped_sensor_material(
            case=case(stage, incident=incident, unrelated=unrelated),
            evidence=evidence,
            records=visible,
            registry=registry(stage),
        )

    stage_one = compiled(1)
    empty = _empty_like(stage_one, case_id="static-gate-empty")
    incident = compiled(2, incident=True)
    corrected = compiled(3)
    revoked = compiled(4)
    unrelated_before = compiled(3, unrelated=True)
    unrelated_after = compiled(4, unrelated=True)
    expectations = (
        PersonaTransitionExpectation(
            transition_id="01-addition",
            kind=PersonaTransitionKind.ADDITION,
            prior_case_id=empty.case_id,
            current_case_id=stage_one.case_id,
            prior_active_source_turns=(),
            current_active_source_turns=(2,),
        ),
        PersonaTransitionExpectation(
            transition_id="02-scoped-exception",
            kind=PersonaTransitionKind.SCOPED_EXCEPTION,
            prior_case_id=stage_one.case_id,
            current_case_id=incident.case_id,
            prior_active_source_turns=(2,),
            current_active_source_turns=(2, 6),
        ),
        PersonaTransitionExpectation(
            transition_id="03-correction",
            kind=PersonaTransitionKind.CORRECTION,
            prior_case_id=stage_one.case_id,
            current_case_id=corrected.case_id,
            prior_active_source_turns=(2,),
            current_active_source_turns=(10,),
        ),
        PersonaTransitionExpectation(
            transition_id="04-revocation",
            kind=PersonaTransitionKind.REVOCATION,
            prior_case_id=corrected.case_id,
            current_case_id=revoked.case_id,
            prior_active_source_turns=(10,),
            current_active_source_turns=(),
        ),
        PersonaTransitionExpectation(
            transition_id="05-neutral",
            kind=PersonaTransitionKind.NEUTRAL,
            prior_case_id=unrelated_before.case_id,
            current_case_id=unrelated_after.case_id,
            prior_active_source_turns=(),
            current_active_source_turns=(),
        ),
    )
    materials = {
        empty.case_id: empty,
        stage_one.case_id: stage_one,
        incident.case_id: incident,
        corrected.case_id: corrected,
        revoked.case_id: revoked,
        unrelated_before.case_id: unrelated_before,
        unrelated_after.case_id: unrelated_after,
    }
    scores = tuple(
        score_transition(
            expectation=expectation,
            prior=materials[expectation.prior_case_id],
            current=materials[expectation.current_case_id],
        )
        for expectation in expectations
    )
    scorecard = build_transition_scorecard(scores)

    preference = route_semantic_features(
        SemanticFeatureVector(
            assertion_kind=SemanticAssertionKind.NORMATIVE,
            norm_strength=SemanticNormStrength.PREFERENCE,
            workflow_structure=SemanticWorkflowStructure.NONE,
            example_intent=SemanticExampleIntent.NONE,
            transition_intent=SemanticTransitionIntent.ADDITION,
        )
    )
    ambiguous = route_semantic_features(
        SemanticFeatureVector(
            assertion_kind=SemanticAssertionKind.MIXED,
            norm_strength=SemanticNormStrength.INVARIANT,
            workflow_structure=SemanticWorkflowStructure.NONE,
            example_intent=SemanticExampleIntent.NONE,
            transition_intent=SemanticTransitionIntent.ADDITION,
        )
    )
    if preference.selected_route is not ArtifactRoute.PREFERENCE:
        raise AssertionError("preference-only meaning was routed invasively")
    if ambiguous.resolution is not SemanticRouteResolution.AMBIGUOUS:
        raise AssertionError("multi-route meaning did not remain review-required")

    substituted = records[0].model_copy(update={"scope": exception_scope})
    try:
        compile_host_scoped_sensor_material(
            case=case(1),
            evidence=build_stage_evidence(history, 1),
            records=(substituted,),
            registry=registry(1),
        )
    except ValueError as error:
        if "noncanonical scope" not in str(error):
            raise
    else:
        raise AssertionError("compiled scope substitution was accepted")

    vacuous_current = _empty_like(revoked, case_id="static-gate-vacuous-revocation")
    vacuous_expectation = expectations[3].model_copy(
        update={"current_case_id": vacuous_current.case_id}
    )
    vacuous_score = score_transition(
        expectation=vacuous_expectation,
        prior=_empty_like(corrected, case_id=corrected.case_id),
        current=vacuous_current,
    )
    if vacuous_score.exact:
        raise AssertionError("doing nothing received revocation credit")

    return PersonaPreV3StaticGateReport(
        checks=_STATIC_GATE_CHECKS,
        scope_transport=scope_audit,
        transition_scorecard=scorecard,
        passed=True,
    )


def persona_static_gate_schemas() -> dict[str, dict[str, object]]:
    return {
        "persona_host_scope_registry.schema.json": PersonaHostScopeRegistry.model_json_schema(),
        "persona_pre_v3_static_gate_report.schema.json": (
            PersonaPreV3StaticGateReport.model_json_schema()
        ),
        "persona_transition_expectation.schema.json": (
            PersonaTransitionExpectation.model_json_schema()
        ),
    }


def write_static_gate_report(root: Path, destination: Path) -> PersonaPreV3StaticGateReport:
    report = run_pre_v3_static_gate(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report
