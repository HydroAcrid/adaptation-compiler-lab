"""Frozen v3 persona protocol and single-persona construction-smoke contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self, cast

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    InteractionObservation,
    SemanticFeatureVector,
    SemanticRouteResolution,
    SemanticTransitionIntent,
)
from adaptation_compiler_lab.automatic_runtime.semantic_routing import route_semantic_features
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaExpectedClaim,
    PersonaHiddenOracle,
    PersonaMaterialClaim,
    PersonaMaterialSnapshot,
    PersonaMaterialSource,
    PersonaObjectiveScore,
    PersonaPublicCase,
    PersonaSensorRecord,
    PersonaStageEvidence,
    render_neutral_guidance,
    score_objective_state,
)
from adaptation_compiler_lab.benchmark.persona_static_gate import (
    PersonaHostScopeBinding,
    PersonaHostScopeRegistry,
    compile_host_scoped_sensor_material,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ArtifactRoute,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Scope,
    Sha256Digest,
    SourceClass,
    TaskRecordRef,
    scope_is_within,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class PersonaV3Protocol(FrozenModel):
    """Preregistered successor design; the full grid is not authorized by this record."""

    protocol_version: Literal["3.0.0"] = "3.0.0"
    benchmark_id: Literal["temper-persona-effectiveness-v3"] = "temper-persona-effectiveness-v3"
    supersedes_failed_benchmark_id: Literal["temper-6a2l-persona-evaluation-v2.1"] = (
        "temper-6a2l-persona-evaluation-v2.1"
    )
    status: Literal["frozen_single_persona_smoke_authorized"] = (
        "frozen_single_persona_smoke_authorized"
    )
    full_grid_persona_count: Literal[6] = 6
    full_grid_case_count: Literal[24] = 24
    stages_per_persona: Literal[4] = 4
    fresh_personas_and_scenarios: Literal[True] = True
    one_persona_per_session: Literal[True] = True
    stage_bounded_evidence_only: Literal[True] = True
    common_host_scope_registry: Literal[True] = True
    model_authored_scope_has_delivery_authority: Literal[False] = False
    model_authored_route_has_promotion_authority: Literal[False] = False
    deterministic_least_invasive_routing: Literal[True] = True
    before_after_lifecycle_scoring: Literal[True] = True
    vacuous_revocation_credit_permitted: Literal[False] = False
    score_slices: tuple[
        Literal[
            "addition",
            "scoped_exception",
            "correction",
            "revocation",
            "neutral",
            "route",
            "scope",
        ],
        ...,
    ] = (
        "addition",
        "scoped_exception",
        "correction",
        "revocation",
        "neutral",
        "route",
        "scope",
    )
    both_objective_lanes_must_pass_before_guidance: Literal[True] = True
    objective_exact_rate_minimum: float = Field(default=0.75, ge=0.75, le=0.75)
    sentinel_accuracy_minimum: float = Field(default=1.0, ge=1.0, le=1.0)
    smoke_persona_count: Literal[1] = 1
    smoke_stage: Literal[2] = 2
    smoke_session_maximum: Literal[3] = 3
    smoke_semantic_sensor_sessions: Literal[1] = 1
    smoke_profile_author_sessions: Literal[1] = 1
    smoke_profile_reviewer_sessions: Literal[1] = 1
    smoke_requires_exact_compiled_state: Literal[True] = True
    smoke_requires_exact_static_state: Literal[True] = True
    smoke_counts_toward_effectiveness_evidence: Literal[False] = False
    full_grid_execution_authorized: Literal[False] = False
    codex_cli_version: Literal["codex-cli 0.146.0"] = "codex-cli 0.146.0"
    codex_binary_digest: Literal[
        "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    ] = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    semantic_sensor_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    semantic_sensor_reasoning_effort: Literal["medium"] = "medium"
    profile_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    profile_reasoning_effort: Literal["xhigh"] = "xhigh"
    saved_chatgpt_authentication_only: Literal[True] = True
    api_keys_permitted: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    sealed_external_validation_access_permitted: Literal[False] = False
    v21_material_mutation_permitted: Literal[False] = False

    @field_validator("score_slices")
    @classmethod
    def slices_are_exact(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        expected = (
            "addition",
            "scoped_exception",
            "correction",
            "revocation",
            "neutral",
            "route",
            "scope",
        )
        if value != expected:
            raise ValueError("v3 protocol requires the complete ordered score-slice set")
        return value


class PersonaV3ProfileClaim(FrozenModel):
    """Behavior and semantic meaning only; trusted code assigns route and scope."""

    statement: NonEmptyStr
    semantic_features: SemanticFeatureVector
    source_turns: Annotated[tuple[int, ...], Field(min_length=1, max_length=4)]

    @field_validator("source_turns")
    @classmethod
    def turns_are_sorted_unique(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("v3 profile source turns must be sorted and unique")
        return value

    @model_validator(mode="after")
    def meaning_routes_deterministically(self) -> Self:
        decision = route_semantic_features(self.semantic_features)
        if decision.resolution is not SemanticRouteResolution.RESOLVED:
            raise ValueError("v3 active profile claim has ambiguous artifact meaning")
        if self.semantic_features.transition_intent is SemanticTransitionIntent.REVOCATION:
            raise ValueError("v3 active profile snapshots cannot contain revocation events")
        if decision.selected_route is None:
            raise ValueError("v3 active profile claim lacks a deterministic route")
        return self

    @property
    def route(self) -> ArtifactRoute:
        route = route_semantic_features(self.semantic_features).selected_route
        if route is None:
            raise ValueError("v3 profile claim has no content route")
        return route


class PersonaV3ProfileSnapshot(FrozenModel):
    stage: Literal[2] = 2
    claims: Annotated[tuple[PersonaV3ProfileClaim, ...], Field(max_length=8)] = ()


class PersonaV3ProfileOutput(FrozenModel):
    output_version: Literal["3.0.0"] = "3.0.0"
    snapshot: PersonaV3ProfileSnapshot
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def output_is_compact(self) -> Self:
        rendered = render_neutral_guidance(
            tuple(
                PersonaMaterialClaim(
                    claim_id=f"schema-preview-{index}",
                    statement=claim.statement,
                    route=claim.route,
                    scope=_SMOKE_BROAD_SCOPE,
                    source_turns=claim.source_turns,
                    evidence_digests=tuple(_PREVIEW_DIGEST for _ in claim.source_turns),
                )
                for index, claim in enumerate(self.snapshot.claims, start=1)
            )
        )
        if len(rendered.encode("utf-8")) > 3_000:
            raise ValueError("v3 profile output exceeds the common guidance ceiling")
        return self


class PersonaV3ProfileAuthorPacket(FrozenModel):
    packet_version: Literal["3.0.0"] = "3.0.0"
    protocol_digest: Sha256Digest
    persona_id: Identifier
    evidence: PersonaStageEvidence
    scope_registry_digest: Sha256Digest

    @model_validator(mode="after")
    def packet_is_exact(self) -> Self:
        if self.persona_id != self.evidence.persona_id or self.evidence.stage != 2:
            raise ValueError("v3 author packet crossed persona or smoke stage")
        return self


class PersonaV3ProfileReviewPacket(FrozenModel):
    packet_version: Literal["3.0.0"] = "3.0.0"
    protocol_digest: Sha256Digest
    persona_id: Identifier
    evidence: PersonaStageEvidence
    scope_registry_digest: Sha256Digest
    draft: PersonaV3ProfileOutput

    @model_validator(mode="after")
    def packet_is_exact(self) -> Self:
        if self.persona_id != self.evidence.persona_id or self.evidence.stage != 2:
            raise ValueError("v3 review packet crossed persona or smoke stage")
        return self


class PersonaV3SmokeFixture(FrozenModel):
    fixture_version: Literal["1.0.0"] = "1.0.0"
    fixture_id: Literal["temper-v3-smoke-sable-stage-2"] = "temper-v3-smoke-sable-stage-2"
    synthetic_only: Literal[True] = True
    counts_toward_effectiveness_evidence: Literal[False] = False
    case: PersonaPublicCase
    evidence: PersonaStageEvidence
    scope_registry: PersonaHostScopeRegistry

    @model_validator(mode="after")
    def fixture_is_exact(self) -> Self:
        if self.case.persona_id != "sable" or self.evidence.persona_id != "sable":
            raise ValueError("v3 smoke requires the one frozen fresh persona")
        if self.case.stage != 2 or self.evidence.stage != 2 or self.scope_registry.stage != 2:
            raise ValueError("v3 smoke requires exactly the second checkpoint")
        if self.scope_registry.persona_id != self.case.persona_id:
            raise ValueError("v3 smoke scope registry crossed personas")
        visible = {message.turn for message in self.evidence.messages}
        if {item.source_turn for item in self.scope_registry.bindings} != visible:
            raise ValueError("v3 smoke requires one exact host scope binding per visible turn")
        return self


class PersonaV3SmokeFreeze(FrozenModel):
    freeze_version: Literal["1.0.0"] = "1.0.0"
    protocol_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    author_packet_digest: Sha256Digest
    semantic_role_contract_digest: Sha256Digest
    semantic_prompt_template_digest: Sha256Digest
    semantic_batch_input_digest: Sha256Digest
    semantic_batch_prompt_digest: Sha256Digest
    semantic_output_schema_digest: Sha256Digest
    profile_output_schema_digest: Sha256Digest
    benchmark_module_digest: Sha256Digest
    runner_module_digest: Sha256Digest
    session_maximum: Literal[3] = 3
    execution_started: Literal[False] = False
    full_grid_execution_authorized: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False


class PersonaV3RoleReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    execution_id: Identifier
    role: Literal["semantic_sensor", "profile_author", "profile_reviewer"]
    persona_id: Literal["sable"] = "sable"
    packet_digest: Sha256Digest
    model: Literal["gpt-5.6-luna", "gpt-5.6-sol"]
    reasoning_effort: Literal["medium", "xhigh"]
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
    trace_digest: Sha256Digest
    encrypted_trace_ref: Sha256Digest
    command_digest: Sha256Digest
    environment_digest: Sha256Digest
    fresh_ephemeral_session: Literal[True] = True
    tool_use_observed: Literal[False] = False
    model_reroute_observed: Literal[False] = False
    session_state_destroyed: Literal[True] = True
    saved_chatgpt_authentication: Literal[True] = True
    api_key_environment_present: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def role_configuration_is_exact(self) -> Self:
        expected = {
            "semantic_sensor": ("gpt-5.6-luna", "medium"),
            "profile_author": ("gpt-5.6-sol", "xhigh"),
            "profile_reviewer": ("gpt-5.6-sol", "xhigh"),
        }[self.role]
        if (self.model, self.reasoning_effort) != expected:
            raise ValueError("v3 role receipt model configuration drifted")
        return self


class PersonaV3SensorResult(FrozenModel):
    result_version: Literal["1.0.0"] = "1.0.0"
    fixture_digest: Sha256Digest
    records: Annotated[tuple[PersonaSensorRecord, ...], Field(min_length=7, max_length=7)]
    execution_receipt: PersonaV3RoleReceipt

    @model_validator(mode="after")
    def result_is_exact(self) -> Self:
        if tuple(item.turn for item in self.records) != tuple(range(1, 8)):
            raise ValueError("v3 smoke sensor result requires exact turns one through seven")
        if self.execution_receipt.role != "semantic_sensor":
            raise ValueError("v3 smoke sensor result has the wrong role receipt")
        return self


class PersonaV3SmokeReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    fixture_id: Literal["temper-v3-smoke-sable-stage-2"] = "temper-v3-smoke-sable-stage-2"
    protocol_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    freeze_digest: Sha256Digest
    scope_registry_digest: Sha256Digest
    role_receipts: Annotated[tuple[PersonaV3RoleReceipt, ...], Field(min_length=3, max_length=3)]
    compiled_material: PersonaMaterialSnapshot
    static_material: PersonaMaterialSnapshot
    compiled_score: PersonaObjectiveScore
    static_score: PersonaObjectiveScore
    nonempty_material_required: Literal[True] = True
    common_scope_registry_verified: Literal[True] = True
    visible_turn_lineage_verified: Literal[True] = True
    condition_leakage_detected: Literal[False] = False
    language_understanding_evaluated: Literal[True] = True
    counts_toward_effectiveness_evidence: Literal[False] = False
    agent_sessions: Literal[3] = 3
    provider_billed_calls: Literal[0] = 0
    full_grid_executed: Literal[False] = False
    full_grid_launch_gate_passed: bool
    passed: bool

    @model_validator(mode="after")
    def report_is_fail_closed(self) -> Self:
        roles = tuple(item.role for item in self.role_receipts)
        if roles != ("semantic_sensor", "profile_author", "profile_reviewer"):
            raise ValueError("v3 smoke requires the exact ordered three-role receipt set")
        if self.compiled_material.source is not PersonaMaterialSource.COMPILED:
            raise ValueError("v3 compiled smoke material has the wrong source")
        if self.static_material.source is not PersonaMaterialSource.STATIC:
            raise ValueError("v3 static smoke material has the wrong source")
        expected = (
            self.compiled_score.exact
            and self.static_score.exact
            and bool(self.compiled_material.claims)
            and bool(self.static_material.claims)
        )
        if self.passed is not expected or self.full_grid_launch_gate_passed is not expected:
            raise ValueError("v3 smoke pass flags do not match exact objective evidence")
        return self


_PREVIEW_DIGEST = "sha256:" + "0" * 64
_SMOKE_BROAD_SCOPE = Scope(subject_ids=("sable",), project_ids=("river-station",))


def bind_v3_profile_output(response: str) -> PersonaV3ProfileOutput:
    """Bind strict model JSON without accepting authored route or scope fields."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    value: object = json.loads(response, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("v3 profile output must be one JSON object")
    snapshot = value.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("v3 profile snapshot must be one JSON object")
    claims = snapshot.get("claims")
    if not isinstance(claims, list):
        raise ValueError("v3 profile claims must be an array")
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("v3 profile claim must be one JSON object")
        turns = claim.get("source_turns")
        if isinstance(turns, list) and all(isinstance(item, int) for item in turns):
            claim["source_turns"] = sorted(turns)
    return PersonaV3ProfileOutput.model_validate_json(canonical_json(value), strict=True)


def persona_v3_profile_output_schema() -> dict[str, object]:
    return cast(dict[str, object], PersonaV3ProfileOutput.model_json_schema())


def build_v3_profile_author_packet(
    protocol: PersonaV3Protocol,
    fixture: PersonaV3SmokeFixture,
) -> PersonaV3ProfileAuthorPacket:
    return PersonaV3ProfileAuthorPacket(
        protocol_digest=canonical_digest(protocol),
        persona_id=fixture.case.persona_id,
        evidence=fixture.evidence,
        scope_registry_digest=canonical_digest(fixture.scope_registry),
    )


def build_v3_profile_review_packet(
    author: PersonaV3ProfileAuthorPacket,
    draft: PersonaV3ProfileOutput,
) -> PersonaV3ProfileReviewPacket:
    return PersonaV3ProfileReviewPacket(
        protocol_digest=author.protocol_digest,
        persona_id=author.persona_id,
        evidence=author.evidence,
        scope_registry_digest=author.scope_registry_digest,
        draft=draft,
    )


def build_v3_observations(
    fixture: PersonaV3SmokeFixture,
) -> tuple[InteractionObservation, ...]:
    """Build the exact trusted observation batch shared by freeze and execution."""

    observed_at = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
    schema_digest = canonical_digest(PersonaV3SmokeFixture.model_json_schema())
    return tuple(
        InteractionObservation(
            observation_id=f"v3-smoke-sable-turn-{message.turn}",
            subject_id=fixture.case.persona_id,
            task_ref=TaskRecordRef(
                record_id="persona-v3-smoke-sable-stage-2",
                record_version="1.0.0",
            ),
            turn_id=f"turn-{message.turn}",
            actor=ActorRef(actor_id=fixture.case.persona_id, kind=ActorKind.USER),
            source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
            text=message.message,
            scope=fixture.scope_registry.binding_for_turn(message.turn).scope,
            observed_at=observed_at + timedelta(minutes=message.turn),
            source_system="local_interaction_runtime",
            source_version="1.0.0",
            source_schema_digest=schema_digest,
        )
        for message in fixture.evidence.messages
    )


def bind_v3_profile_material(
    *,
    fixture: PersonaV3SmokeFixture,
    reviewed: PersonaV3ProfileOutput,
) -> PersonaMaterialSnapshot:
    """Route semantic meaning and bind scope exclusively through trusted code."""

    visible = {item.turn: item for item in fixture.evidence.messages}
    claims: list[PersonaMaterialClaim] = []
    for proposal in reviewed.snapshot.claims:
        if any(turn not in visible for turn in proposal.source_turns):
            raise ValueError("v3 profile cited hidden or future evidence")
        binding = fixture.scope_registry.binding_for_turn(proposal.source_turns[-1])
        claim_digest = canonical_digest(
            {
                "persona_id": fixture.case.persona_id,
                "proposal": proposal.model_dump(mode="json", round_trip=True),
                "scope_binding_id": binding.binding_id,
            }
        ).removeprefix("sha256:")
        claims.append(
            PersonaMaterialClaim(
                claim_id=f"claim-{claim_digest[:24]}",
                statement=proposal.statement,
                route=proposal.route,
                scope=binding.scope,
                source_turns=proposal.source_turns,
                evidence_digests=tuple(
                    canonical_digest(visible[turn]) for turn in proposal.source_turns
                ),
            )
        )
    applicable = tuple(
        item for item in claims if scope_is_within(fixture.case.current_scope, item.scope)
    )
    return PersonaMaterialSnapshot(
        case_id=fixture.case.case_id,
        persona_id=fixture.case.persona_id,
        source=PersonaMaterialSource.STATIC,
        claims=applicable,
        target_guidance=render_neutral_guidance(applicable),
        evidence_checkpoint_digest=fixture.evidence.content_digest,
        independently_reviewed=True,
    )


def bind_v3_compiled_material(
    *,
    fixture: PersonaV3SmokeFixture,
    records: tuple[PersonaSensorRecord, ...],
) -> PersonaMaterialSnapshot:
    return compile_host_scoped_sensor_material(
        case=fixture.case,
        evidence=fixture.evidence,
        records=records,
        registry=fixture.scope_registry,
    )


def score_v3_smoke_material(
    fixture: PersonaV3SmokeFixture,
    oracle: PersonaHiddenOracle,
    material: PersonaMaterialSnapshot,
) -> PersonaObjectiveScore:
    if fixture.case.case_id != oracle.case_id or fixture.case.persona_id != oracle.persona_id:
        raise ValueError("v3 smoke oracle crossed its public fixture")
    return score_objective_state(material, oracle)


def build_v3_smoke_fixture() -> PersonaV3SmokeFixture:
    """Return the one fresh public synthetic persona used only for instrument smoke."""

    from adaptation_compiler_lab.benchmark.persona_instrument import PersonaEvidenceMessage

    broad = Scope(subject_ids=("sable",), project_ids=("river-station",))
    incident = Scope(
        subject_ids=("sable",),
        project_ids=("river-station",),
        activation_conditions=("production_incident",),
    )
    messages = (
        PersonaEvidenceMessage(
            turn=1,
            message="Draft a short River Station update before the team standup.",
        ),
        PersonaEvidenceMessage(
            turn=2,
            message=(
                "river updates land better for me when the outcome comes first, then the "
                "evidence. keep that as my normal pattern here."
            ),
        ),
        PersonaEvidenceMessage(
            turn=3,
            message="Make this particular update easy to scan on a phone.",
        ),
        PersonaEvidenceMessage(
            turn=4,
            message="River Station has a production incident and on-call needs a handoff.",
        ),
        PersonaEvidenceMessage(
            turn=5,
            message="Include the first two recovery checks in this handoff.",
        ),
        PersonaEvidenceMessage(
            turn=6,
            message=(
                "For River production incidents going forward, put the immediate recovery "
                "commands before the outcome summary; that's the narrow exception."
            ),
        ),
        PersonaEvidenceMessage(
            turn=7,
            message="Do not change any files for this request.",
        ),
    )
    evidence = PersonaStageEvidence(
        persona_id="sable",
        stage=2,
        checkpoint_turn=7,
        messages=messages,
    )
    bindings = tuple(
        PersonaHostScopeBinding(
            binding_id=f"scope-sable-turn-{message.turn}",
            source_turn=message.turn,
            scope=(broad if message.turn <= 3 else incident),
        )
        for message in messages
    )
    registry = PersonaHostScopeRegistry(
        persona_id="sable",
        stage=2,
        bindings=bindings,
    )
    case = PersonaPublicCase(
        case_id="sable-v3-smoke-stage-2",
        persona_id="sable",
        stage=2,
        checkpoint_turn=7,
        current_scope=incident,
        context_label="project:river-station:production-incident",
        scenario="Prepare a River Station production-incident handoff for on-call.",
    )
    return PersonaV3SmokeFixture(
        case=case,
        evidence=evidence,
        scope_registry=registry,
    )


def build_v3_smoke_oracle(fixture: PersonaV3SmokeFixture) -> PersonaHiddenOracle:
    """Return the separately frozen oracle, never included in a construction packet."""

    broad = fixture.scope_registry.binding_for_turn(2).scope
    incident = fixture.scope_registry.binding_for_turn(6).scope
    return PersonaHiddenOracle(
        case_id=fixture.case.case_id,
        persona_id=fixture.case.persona_id,
        sentinel=False,
        active_claims=(
            PersonaExpectedClaim(source_turn=2, route=ArtifactRoute.PREFERENCE, scope=broad),
            PersonaExpectedClaim(source_turn=6, route=ArtifactRoute.PROCEDURE, scope=incident),
        ),
        forbidden_source_turns=(1, 3, 4, 5, 7),
    )


def persona_v3_schemas() -> dict[str, dict[str, object]]:
    return {
        "persona-v3-profile-output.schema.json": PersonaV3ProfileOutput.model_json_schema(),
        "persona-v3-protocol.schema.json": PersonaV3Protocol.model_json_schema(),
        "persona-v3-role-receipt.schema.json": PersonaV3RoleReceipt.model_json_schema(),
        "persona-v3-sensor-result.schema.json": PersonaV3SensorResult.model_json_schema(),
        "persona-v3-smoke-fixture.schema.json": PersonaV3SmokeFixture.model_json_schema(),
        "persona-v3-smoke-freeze.schema.json": PersonaV3SmokeFreeze.model_json_schema(),
        "persona-v3-smoke-report.schema.json": PersonaV3SmokeReport.model_json_schema(),
    }
