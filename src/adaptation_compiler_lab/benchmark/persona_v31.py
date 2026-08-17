"""Fresh replacement construction smoke after the ambiguous persona v3 fixture."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.models import InteractionObservation
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaEvidenceMessage,
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
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3ProfileAuthorPacket,
    PersonaV3ProfileOutput,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ArtifactRoute,
    FrozenModel,
    Identifier,
    Scope,
    Sha256Digest,
    SourceClass,
    TaskRecordRef,
    scope_is_within,
)
from adaptation_compiler_lab.serialization import canonical_digest


class PersonaV31Protocol(FrozenModel):
    protocol_version: Literal["3.1.0"] = "3.1.0"
    benchmark_id: Literal["temper-persona-v31-replacement-smoke"] = (
        "temper-persona-v31-replacement-smoke"
    )
    supersedes_failed_smoke: Literal["temper-v3-smoke-sable-stage-2"] = (
        "temper-v3-smoke-sable-stage-2"
    )
    status: Literal["frozen_replacement_smoke_authorized"] = "frozen_replacement_smoke_authorized"
    fresh_persona_and_wording: Literal[True] = True
    nonsequential_soft_preference: Literal[True] = True
    separate_triggered_procedure: Literal[True] = True
    lifecycle_correction_under_test: Literal[False] = False
    positive_example_under_test: Literal[False] = False
    common_host_scope_registry: Literal[True] = True
    deterministic_route_and_scope_authority: Literal[True] = True
    oracle_separate_from_construction_packets: Literal[True] = True
    session_maximum: Literal[3] = 3
    exact_compiled_state_required: Literal[True] = True
    exact_static_state_required: Literal[True] = True
    counts_toward_effectiveness_evidence: Literal[False] = False
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


class PersonaV31Fixture(FrozenModel):
    fixture_version: Literal["1.0.0"] = "1.0.0"
    fixture_id: Literal["temper-v31-smoke-nola-stage-2"] = "temper-v31-smoke-nola-stage-2"
    synthetic_only: Literal[True] = True
    counts_toward_effectiveness_evidence: Literal[False] = False
    case: PersonaPublicCase
    evidence: PersonaStageEvidence
    scope_registry: PersonaHostScopeRegistry

    @model_validator(mode="after")
    def fixture_is_exact(self) -> Self:
        if self.case.persona_id != "nola" or self.evidence.persona_id != "nola":
            raise ValueError("v3.1 replacement smoke requires the fresh Nola persona")
        if self.case.stage != 2 or self.evidence.stage != 2 or self.scope_registry.stage != 2:
            raise ValueError("v3.1 replacement smoke requires checkpoint two")
        if self.scope_registry.persona_id != self.case.persona_id:
            raise ValueError("v3.1 scope registry crossed personas")
        visible = {message.turn for message in self.evidence.messages}
        if {item.source_turn for item in self.scope_registry.bindings} != visible:
            raise ValueError("v3.1 requires one host scope binding per visible turn")
        return self


class PersonaV31Freeze(FrozenModel):
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


class PersonaV31RoleReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    execution_id: Identifier
    role: Literal["semantic_sensor", "profile_author", "profile_reviewer"]
    persona_id: Literal["nola"] = "nola"
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
            raise ValueError("v3.1 role receipt model configuration drifted")
        return self


class PersonaV31SensorResult(FrozenModel):
    result_version: Literal["1.0.0"] = "1.0.0"
    fixture_digest: Sha256Digest
    records: Annotated[tuple[PersonaSensorRecord, ...], Field(min_length=7, max_length=7)]
    execution_receipt: PersonaV31RoleReceipt

    @model_validator(mode="after")
    def result_is_exact(self) -> Self:
        if tuple(item.turn for item in self.records) != tuple(range(1, 8)):
            raise ValueError("v3.1 sensor result requires turns one through seven")
        if self.execution_receipt.role != "semantic_sensor":
            raise ValueError("v3.1 sensor result has the wrong role receipt")
        return self


class PersonaV31Report(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    fixture_id: Literal["temper-v31-smoke-nola-stage-2"] = "temper-v31-smoke-nola-stage-2"
    protocol_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    freeze_digest: Sha256Digest
    scope_registry_digest: Sha256Digest
    role_receipts: Annotated[tuple[PersonaV31RoleReceipt, ...], Field(min_length=3, max_length=3)]
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
    successful_agent_sessions: Literal[3] = 3
    provider_billed_calls: Literal[0] = 0
    full_grid_executed: Literal[False] = False
    full_grid_launch_gate_passed: bool
    passed: bool

    @model_validator(mode="after")
    def report_is_fail_closed(self) -> Self:
        if tuple(item.role for item in self.role_receipts) != (
            "semantic_sensor",
            "profile_author",
            "profile_reviewer",
        ):
            raise ValueError("v3.1 requires the ordered three-role receipt set")
        if self.compiled_material.source is not PersonaMaterialSource.COMPILED:
            raise ValueError("v3.1 compiled material has the wrong source")
        if self.static_material.source is not PersonaMaterialSource.STATIC:
            raise ValueError("v3.1 static material has the wrong source")
        expected = (
            self.compiled_score.exact
            and self.static_score.exact
            and bool(self.compiled_material.claims)
            and bool(self.static_material.claims)
        )
        if self.passed is not expected or self.full_grid_launch_gate_passed is not expected:
            raise ValueError("v3.1 pass flags do not match objective evidence")
        return self


def build_v31_fixture() -> PersonaV31Fixture:
    broad = Scope(subject_ids=("nola",), project_ids=("copper-finch",))
    incident = Scope(
        subject_ids=("nola",),
        project_ids=("copper-finch",),
        activation_conditions=("production_incident",),
    )
    messages = (
        PersonaEvidenceMessage(turn=1, message="Give me a quick summary of Copper Finch."),
        PersonaEvidenceMessage(
            turn=2,
            message=(
                "For Copper Finch work going forward, I prefer plain, literal language over "
                "clever phrasing."
            ),
        ),
        PersonaEvidenceMessage(turn=3, message="Keep this answer under eighty words."),
        PersonaEvidenceMessage(
            turn=4,
            message="We are investigating a production incident in Copper Finch.",
        ),
        PersonaEvidenceMessage(turn=5, message="List the current symptoms."),
        PersonaEvidenceMessage(
            turn=6,
            message=(
                "For future Copper Finch production incidents, always check service health, "
                "then recent deploys, then queue depth."
            ),
        ),
        PersonaEvidenceMessage(
            turn=7,
            message="Do not edit any files in this response.",
        ),
    )
    evidence = PersonaStageEvidence(
        persona_id="nola",
        stage=2,
        checkpoint_turn=7,
        messages=messages,
    )
    registry = PersonaHostScopeRegistry(
        persona_id="nola",
        stage=2,
        bindings=tuple(
            PersonaHostScopeBinding(
                binding_id=f"scope-nola-turn-{message.turn}",
                source_turn=message.turn,
                scope=(broad if message.turn <= 3 else incident),
            )
            for message in messages
        ),
    )
    case = PersonaPublicCase(
        case_id="nola-v31-smoke-stage-2",
        persona_id="nola",
        stage=2,
        checkpoint_turn=7,
        current_scope=incident,
        context_label="project:copper-finch:production-incident",
        scenario="Prepare a concise Copper Finch production-incident status note.",
    )
    return PersonaV31Fixture(case=case, evidence=evidence, scope_registry=registry)


def build_v31_oracle(fixture: PersonaV31Fixture) -> PersonaHiddenOracle:
    return PersonaHiddenOracle(
        case_id=fixture.case.case_id,
        persona_id=fixture.case.persona_id,
        sentinel=False,
        active_claims=(
            PersonaExpectedClaim(
                source_turn=2,
                route=ArtifactRoute.PREFERENCE,
                scope=fixture.scope_registry.binding_for_turn(2).scope,
            ),
            PersonaExpectedClaim(
                source_turn=6,
                route=ArtifactRoute.PROCEDURE,
                scope=fixture.scope_registry.binding_for_turn(6).scope,
            ),
        ),
        forbidden_source_turns=(1, 3, 4, 5, 7),
    )


def build_v31_author_packet(
    protocol: PersonaV31Protocol,
    fixture: PersonaV31Fixture,
) -> PersonaV3ProfileAuthorPacket:
    return PersonaV3ProfileAuthorPacket(
        protocol_digest=canonical_digest(protocol),
        persona_id=fixture.case.persona_id,
        evidence=fixture.evidence,
        scope_registry_digest=canonical_digest(fixture.scope_registry),
    )


def build_v31_observations(fixture: PersonaV31Fixture) -> tuple[InteractionObservation, ...]:
    observed_at = datetime(2026, 8, 17, 22, 0, tzinfo=UTC)
    schema_digest = canonical_digest(PersonaV31Fixture.model_json_schema())
    return tuple(
        InteractionObservation(
            observation_id=f"v31-smoke-nola-turn-{message.turn}",
            subject_id=fixture.case.persona_id,
            task_ref=TaskRecordRef(
                record_id="persona-v31-smoke-nola-stage-2",
                record_version="1.0.0",
            ),
            turn_id=f"turn-{message.turn}",
            actor=ActorRef(actor_id=fixture.case.persona_id, kind=ActorKind.USER),
            source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
            text=message.message,
            scope=fixture.scope_registry.binding_for_turn(message.turn).scope,
            observed_at=observed_at + timedelta(minutes=message.turn),
            source_system="local_interaction_runtime",
            source_version="persona-v31-smoke",
            source_schema_digest=schema_digest,
        )
        for message in fixture.evidence.messages
    )


def bind_v31_profile_material(
    *,
    fixture: PersonaV31Fixture,
    reviewed: PersonaV3ProfileOutput,
) -> PersonaMaterialSnapshot:
    visible = {item.turn: item for item in fixture.evidence.messages}
    claims: list[PersonaMaterialClaim] = []
    for proposal in reviewed.snapshot.claims:
        if any(turn not in visible for turn in proposal.source_turns):
            raise ValueError("v3.1 profile cited hidden or future evidence")
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


def bind_v31_compiled_material(
    *, fixture: PersonaV31Fixture, records: tuple[PersonaSensorRecord, ...]
) -> PersonaMaterialSnapshot:
    return compile_host_scoped_sensor_material(
        case=fixture.case,
        evidence=fixture.evidence,
        records=records,
        registry=fixture.scope_registry,
    )


def score_v31_material(
    fixture: PersonaV31Fixture,
    oracle: PersonaHiddenOracle,
    material: PersonaMaterialSnapshot,
) -> PersonaObjectiveScore:
    if fixture.case.case_id != oracle.case_id or fixture.case.persona_id != oracle.persona_id:
        raise ValueError("v3.1 oracle crossed its public fixture")
    return score_objective_state(material, oracle)


def persona_v31_schemas() -> dict[str, dict[str, object]]:
    return {
        "persona-v31-protocol.schema.json": PersonaV31Protocol.model_json_schema(),
        "persona-v31-fixture.schema.json": PersonaV31Fixture.model_json_schema(),
        "persona-v31-freeze.schema.json": PersonaV31Freeze.model_json_schema(),
        "persona-v31-role-receipt.schema.json": PersonaV31RoleReceipt.model_json_schema(),
        "persona-v31-sensor-result.schema.json": PersonaV31SensorResult.model_json_schema(),
        "persona-v31-report.schema.json": PersonaV31Report.model_json_schema(),
    }
