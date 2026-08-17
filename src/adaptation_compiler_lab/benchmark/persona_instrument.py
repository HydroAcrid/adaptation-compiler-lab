"""Hardened v2.1 persona instrument with stage-bounded evidence and objective state scoring."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import Counter
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    AutomationDisposition,
    DetectedFeedback,
    FeedbackDetectorMode,
    FeedbackSignalKind,
    InteractionObservation,
    SemanticFeedbackInterpretation,
    SemanticTransitionIntent,
)
from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaEvidenceHistory,
    PersonaPreference,
)
from adaptation_compiler_lab.domain import (
    ArtifactRoute,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Scope,
    Sha256Digest,
    scope_is_within,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_CHECKPOINTS = (3, 7, 11, 15)
_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "condition",
        "expected_active_trait_ids",
        "expected_claims",
        "expected_trait_ids",
        "forbidden_claims",
        "forbidden_trait_ids",
        "judge_summary",
        "sentinel",
        "transition",
    }
)
_FORBIDDEN_PRESENTATION_CUES = (
    "compiled adaptation",
    "compiled_adaptation",
    "controlled_sentinel",
    "strong static",
    "strong_static_profile",
)


class PersonaMaterialSource(StrEnum):
    COMPILED = "compiled"
    STATIC = "static"


class PersonaEvidenceMessage(FrozenModel):
    """The only interaction fields visible to construction or evaluation roles."""

    turn: Annotated[int, Field(ge=1, le=15)]
    message: NonEmptyStr


class PersonaStageEvidence(FrozenModel):
    """One chronological evidence prefix with labels and future turns removed."""

    packet_version: Literal["2.1.0"] = "2.1.0"
    persona_id: Identifier
    stage: Annotated[int, Field(ge=1, le=4)]
    checkpoint_turn: Literal[3, 7, 11, 15]
    messages: Annotated[tuple[PersonaEvidenceMessage, ...], Field(min_length=3, max_length=15)]

    @model_validator(mode="after")
    def prefix_is_exact(self) -> Self:
        if self.checkpoint_turn != _CHECKPOINTS[self.stage - 1]:
            raise ValueError("persona evidence stage/checkpoint mismatch")
        if tuple(item.turn for item in self.messages) != tuple(range(1, self.checkpoint_turn + 1)):
            raise ValueError("persona evidence must be one complete stage-bounded prefix")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PersonaPublicCase(FrozenModel):
    """Scenario information safe for construction and blind evaluation."""

    case_id: Identifier
    persona_id: Identifier
    stage: Annotated[int, Field(ge=1, le=4)]
    checkpoint_turn: Literal[3, 7, 11, 15]
    current_scope: Scope
    context_label: NonEmptyStr
    scenario: NonEmptyStr

    @model_validator(mode="after")
    def checkpoint_matches_stage(self) -> Self:
        if self.checkpoint_turn != _CHECKPOINTS[self.stage - 1]:
            raise ValueError("persona public case stage/checkpoint mismatch")
        return self


class PersonaExpectedClaim(FrozenModel):
    """Private oracle entry used only by deterministic scoring after construction freezes."""

    source_turn: Annotated[int, Field(ge=1, le=15)]
    route: ArtifactRoute
    scope: Scope


class PersonaHiddenOracle(FrozenModel):
    """Private expected state that must never enter author, compiler, or judge packets."""

    case_id: Identifier
    persona_id: Identifier
    sentinel: bool
    active_claims: tuple[PersonaExpectedClaim, ...]
    forbidden_source_turns: tuple[int, ...]

    @field_validator("forbidden_source_turns")
    @classmethod
    def forbidden_turns_are_sorted_unique(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("forbidden source turns must be sorted and unique")
        return value

    @model_validator(mode="after")
    def active_claims_are_unique(self) -> Self:
        turns = tuple(item.source_turn for item in self.active_claims)
        if turns != tuple(sorted(set(turns))):
            raise ValueError("expected active claims must be sorted and unique by source turn")
        if set(turns) & set(self.forbidden_source_turns):
            raise ValueError("active and forbidden source turns overlap")
        return self


class PersonaModelProfileClaim(FrozenModel):
    """Identity-free claim authored from visible evidence."""

    statement: NonEmptyStr
    route: ArtifactRoute
    scope: Scope
    source_turns: Annotated[tuple[int, ...], Field(min_length=1, max_length=4)]

    @field_validator("source_turns")
    @classmethod
    def source_turns_are_sorted_unique(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("profile source turns must be sorted and unique")
        return value


class PersonaModelProfileSnapshot(FrozenModel):
    stage: Annotated[int, Field(ge=1, le=4)]
    claims: Annotated[tuple[PersonaModelProfileClaim, ...], Field(max_length=8)] = ()


class PersonaModelProfileOutput(FrozenModel):
    """Model-facing output shared by the author and the independent reviewer."""

    output_version: Literal["2.1.0"] = "2.1.0"
    snapshot: PersonaModelProfileSnapshot
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def snapshot_is_bounded(self) -> Self:
        rendered = (
            "No durable instruction is applicable to this scenario."
            if not self.snapshot.claims
            else "\n".join(f"- {item.statement}" for item in self.snapshot.claims)
        )
        if len(rendered.encode("utf-8")) > 3_000:
            raise ValueError("profile snapshot exceeds the common guidance byte ceiling")
        return self


_PROFILE_SCOPE_SET_FIELDS = (
    "subject_ids",
    "workspace_ids",
    "project_ids",
    "repository_ids",
    "task_classes",
    "environment_ids",
    "target_families",
    "activation_conditions",
    "exclusions",
)


def bind_model_profile_output(response: str) -> PersonaModelProfileOutput:
    """Canonicalize ordering for set-like model fields, then apply strict domain validation."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    value: object = json.loads(response, parse_constant=reject_constant)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("profile output must be one JSON object")
    root = cast(dict[str, object], value)
    snapshot = root.get("snapshot")
    if not isinstance(snapshot, dict) or not all(isinstance(key, str) for key in snapshot):
        raise ValueError("profile output snapshot must be one JSON object")
    claims = snapshot.get("claims")
    if not isinstance(claims, list):
        raise ValueError("profile output claims must be an array")
    for raw_claim in claims:
        if not isinstance(raw_claim, dict) or not all(isinstance(key, str) for key in raw_claim):
            raise ValueError("profile output claim must be one JSON object")
        claim = cast(dict[str, object], raw_claim)
        source_turns = claim.get("source_turns")
        if isinstance(source_turns, list) and all(isinstance(item, int) for item in source_turns):
            claim["source_turns"] = sorted(source_turns)
        scope = claim.get("scope")
        if not isinstance(scope, dict) or not all(isinstance(key, str) for key in scope):
            raise ValueError("profile output scope must be one JSON object")
        for field in _PROFILE_SCOPE_SET_FIELDS:
            field_value = scope.get(field)
            if isinstance(field_value, list) and all(isinstance(item, str) for item in field_value):
                scope[field] = sorted(field_value)
    return PersonaModelProfileOutput.model_validate_json(canonical_json(root), strict=True)


class PersonaProfileAuthorPacket(FrozenModel):
    packet_version: Literal["2.1.0"] = "2.1.0"
    persona_id: Identifier
    evidence: PersonaStageEvidence

    @model_validator(mode="after")
    def persona_is_exact(self) -> Self:
        if self.evidence.persona_id != self.persona_id:
            raise ValueError("profile author packet crossed personas")
        return self


class PersonaProfileReviewPacket(FrozenModel):
    packet_version: Literal["2.1.0"] = "2.1.0"
    persona_id: Identifier
    evidence: PersonaStageEvidence
    draft: PersonaModelProfileOutput

    @model_validator(mode="after")
    def persona_and_stage_are_exact(self) -> Self:
        if self.evidence.persona_id != self.persona_id:
            raise ValueError("profile review packet crossed personas")
        if self.draft.snapshot.stage != self.evidence.stage:
            raise ValueError("profile review packet crossed evidence stages")
        return self


class PersonaMaterialClaim(FrozenModel):
    claim_id: Identifier
    statement: NonEmptyStr
    route: ArtifactRoute
    scope: Scope
    source_turns: Annotated[tuple[int, ...], Field(min_length=1, max_length=4)]
    evidence_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=4)]
    interpretation_receipt_digest: Sha256Digest | None = None
    detection_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def lineage_is_exact(self) -> Self:
        if self.source_turns != tuple(sorted(set(self.source_turns))):
            raise ValueError("material source turns must be sorted and unique")
        if len(self.source_turns) != len(self.evidence_digests):
            raise ValueError("every source turn requires one exact evidence digest")
        semantic = self.interpretation_receipt_digest is not None
        if semantic != (self.detection_digest is not None):
            raise ValueError("semantic material requires both interpretation and detection lineage")
        return self


class PersonaMaterialSnapshot(FrozenModel):
    snapshot_version: Literal["2.1.0"] = "2.1.0"
    case_id: Identifier
    persona_id: Identifier
    source: PersonaMaterialSource
    claims: tuple[PersonaMaterialClaim, ...]
    target_guidance: NonEmptyStr
    evidence_checkpoint_digest: Sha256Digest
    independently_reviewed: bool

    @model_validator(mode="after")
    def material_is_neutral_and_unique(self) -> Self:
        if len({item.claim_id for item in self.claims}) != len(self.claims):
            raise ValueError("persona material claim IDs must be unique")
        if self.target_guidance != render_neutral_guidance(self.claims):
            raise ValueError("persona material bypassed the common neutral renderer")
        if self.independently_reviewed is not (self.source is PersonaMaterialSource.STATIC):
            raise ValueError("only the static comparator must be independently reviewed")
        return self


class PersonaSensorRecord(FrozenModel):
    """One reviewed, receipted semantic decision before deterministic lifecycle compilation."""

    record_version: Literal["2.1.0"] = "2.1.0"
    persona_id: Identifier
    turn: Annotated[int, Field(ge=1, le=15)]
    observation_digest: Sha256Digest
    interpretation_receipt_digest: Sha256Digest
    detection_digest: Sha256Digest
    claim_id: Identifier | None = None
    signal_kind: FeedbackSignalKind | None = None
    transition_intent: SemanticTransitionIntent | None = None
    statement: NonEmptyStr | None = None
    route: ArtifactRoute | None = None
    scope: Scope
    affected_claim_id: Identifier | None = None
    approved: bool
    review_receipt_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def decision_shape_is_coherent(self) -> Self:
        actionable = self.signal_kind is not None
        if actionable != (self.transition_intent is not None):
            raise ValueError("sensor transition must match actionable state")
        if self.approved and self.review_receipt_digest is None:
            raise ValueError("approved semantic learning requires a review receipt")
        if not actionable:
            if (
                any(
                    value is not None
                    for value in (
                        self.claim_id,
                        self.statement,
                        self.route,
                        self.affected_claim_id,
                    )
                )
                or self.approved
            ):
                raise ValueError("no-signal sensor record cannot change learning")
        elif self.signal_kind is FeedbackSignalKind.REVOCATION:
            if (
                (self.approved and self.affected_claim_id is None)
                or self.claim_id is not None
                or self.statement is not None
                or self.route is not None
                or self.transition_intent is not SemanticTransitionIntent.REVOCATION
            ):
                raise ValueError("revocation sensor record has an invalid lifecycle shape")
        elif self.claim_id is None or self.statement is None or self.route is None:
            raise ValueError("content sensor record requires a claim, statement, and route")
        elif self.transition_intent is SemanticTransitionIntent.REVOCATION:
            raise ValueError("content sensor record cannot carry revocation lifecycle intent")
        elif self.transition_intent is SemanticTransitionIntent.CORRECTION:
            if self.approved and self.affected_claim_id is None:
                raise ValueError("correction sensor record requires one exact active target")
        elif self.affected_claim_id is not None:
            raise ValueError("addition sensor record cannot target an earlier claim")
        return self


class PersonaV21SensorTarget(FrozenModel):
    """Trusted host binding from one correcting or revoking turn to earlier evidence."""

    turn: Annotated[int, Field(ge=1, le=11)]
    affected_source_turn: Annotated[int, Field(ge=1, le=10)]

    @model_validator(mode="after")
    def target_precedes_transition(self) -> Self:
        if self.affected_source_turn >= self.turn:
            raise ValueError("sensor target must precede the correcting or revoking turn")
        return self


class PersonaV21SensorBatch(FrozenModel):
    """One stage-bounded semantic batch for exactly one persona."""

    batch_version: Literal["2.1.0"] = "2.1.0"
    batch_id: Identifier
    persona_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    messages: Annotated[tuple[PersonaEvidenceMessage, ...], Field(min_length=3, max_length=4)]
    scope: Scope
    target_bindings: tuple[PersonaV21SensorTarget, ...] = ()
    construction_cutoff: NonEmptyStr

    @model_validator(mode="after")
    def segment_is_exact_and_host_bindings_are_visible(self) -> Self:
        expected = {
            1: tuple(range(1, 4)),
            2: tuple(range(4, 8)),
            3: tuple(range(8, 12)),
        }[self.stage]
        turns = tuple(item.turn for item in self.messages)
        if turns != expected:
            raise ValueError("semantic batch must contain one exact incremental stage segment")
        bindings = tuple(item.turn for item in self.target_bindings)
        if bindings != tuple(sorted(set(bindings))) or any(turn not in turns for turn in bindings):
            raise ValueError("sensor target bindings must be unique and visible in the batch")
        return self


class PersonaObjectiveScore(FrozenModel):
    case_id: Identifier
    source: PersonaMaterialSource
    expected_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    missing_source_turns: tuple[int, ...]
    unexpected_source_turns: tuple[int, ...]
    forbidden_source_turns: tuple[int, ...]
    route_mismatch_source_turns: tuple[int, ...]
    scope_mismatch_source_turns: tuple[int, ...]
    lineage_complete: bool
    exact: bool


class PersonaV21Protocol(FrozenModel):
    """Executable preregistration requirements frozen before any v2.1 construction."""

    protocol_version: Literal["2.1.0"] = "2.1.0"
    benchmark_id: Literal["temper-6a2l-persona-evaluation-v2.1"] = (
        "temper-6a2l-persona-evaluation-v2.1"
    )
    supersedes_unexecuted_benchmark_id: Literal["temper-6a2l-persona-evaluation-v2"] = (
        "temper-6a2l-persona-evaluation-v2"
    )
    status: Literal["frozen_design_not_executed"] = "frozen_design_not_executed"
    persona_count: Literal[6] = 6
    case_count: Literal[24] = 24
    stages_per_persona: Literal[4] = 4
    fresh_personas_and_scenarios: Literal[True] = True
    v1_case_content_reuse_permitted: Literal[False] = False
    required_language_phenomena: tuple[
        Literal[
            "acronym_or_shorthand",
            "ambiguous_correction",
            "exact_revocation",
            "implicit_preference",
            "misspelling_or_bad_grammar",
            "narrow_context_exception",
            "one_off_request_near_miss",
            "quoted_untrusted_instruction",
        ],
        ...,
    ] = (
        "acronym_or_shorthand",
        "ambiguous_correction",
        "exact_revocation",
        "implicit_preference",
        "misspelling_or_bad_grammar",
        "narrow_context_exception",
        "one_off_request_near_miss",
        "quoted_untrusted_instruction",
    )
    hidden_oracle_outside_construction: Literal[True] = True
    stage_bounded_evidence_only: Literal[True] = True
    same_eligible_evidence_for_both_conditions: Literal[True] = True
    condition_mapping_and_seed_outside_construction: Literal[True] = True
    static_reviewer_cannot_see_compiled_material: Literal[True] = True
    common_guidance_byte_ceiling: Literal[3000] = 3000
    static_author_sessions: Literal[24] = 24
    static_reviewer_sessions: Literal[24] = 24
    semantic_sensor_source: Literal["live_isolated_sensor_plus_deterministic_policy"] = (
        "live_isolated_sensor_plus_deterministic_policy"
    )
    semantic_sensor_max_sessions: Literal[18] = 18
    guidance_judge_sessions: Literal[48] = 48
    guidance_adjudicator_max_sessions: Literal[6] = 6
    total_session_maximum: Literal[120] = 120
    codex_cli_version: Literal["codex-cli 0.146.0"] = "codex-cli 0.146.0"
    codex_binary_digest: Literal[
        "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    ] = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    codex_schema_bundle_digest: Literal[
        "sha256:1af35d724750f55eebc5e76d1ce7a86e6024d5b31360137894f2f6b6ee7924ba"
    ] = "sha256:1af35d724750f55eebc5e76d1ce7a86e6024d5b31360137894f2f6b6ee7924ba"
    runtime_pin_manifest_digest: Literal[
        "sha256:7b2722810a907797638bc20c80cf2fe890c26ecbf448d52dc9ed7b0051808fca"
    ] = "sha256:7b2722810a907797638bc20c80cf2fe890c26ecbf448d52dc9ed7b0051808fca"
    semantic_sensor_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    semantic_sensor_reasoning_effort: Literal["medium"] = "medium"
    profile_author_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    profile_author_reasoning_effort: Literal["xhigh"] = "xhigh"
    profile_reviewer_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    profile_reviewer_reasoning_effort: Literal["xhigh"] = "xhigh"
    guidance_judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    guidance_judge_reasoning_effort: Literal["xhigh"] = "xhigh"
    guidance_adjudicator_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    guidance_adjudicator_reasoning_effort: Literal["max"] = "max"
    semantic_sensor_timeout_seconds: Literal[180] = 180
    profile_role_timeout_seconds: Literal[600] = 600
    judge_timeout_seconds: Literal[600] = 600
    adjudicator_timeout_seconds: Literal[900] = 900
    one_persona_per_session: Literal[True] = True
    saved_chatgpt_authentication_only: Literal[True] = True
    provider_billed_calls: Literal[0] = 0
    external_validation_access_permitted: Literal[False] = False
    learning_state_scoring: Literal["deterministic_hidden_oracle"] = "deterministic_hidden_oracle"
    guidance_scoring: Literal["blind_counterbalanced_fresh_judges"] = (
        "blind_counterbalanced_fresh_judges"
    )
    objective_exact_rate_minimum: float = Field(default=0.75, ge=0, le=1)
    static_objective_exact_rate_minimum: float = Field(default=0.75, ge=0, le=1)
    guidance_agreement_rate_minimum: float = Field(default=0.75, ge=0, le=1)
    guidance_adjudication_rate_maximum: float = Field(default=0.25, ge=0, le=1)
    guidance_unresolved_rate_maximum: float = Field(default=0.10, ge=0, le=1)
    sentinel_accuracy_minimum: float = Field(default=1.0, ge=1.0, le=1.0)
    false_activation_maximum: Literal[0] = 0
    lifecycle_leak_maximum: Literal[0] = 0
    target_guidance_utf8_bytes_maximum: Literal[3000] = 3000
    invalid_run_retry_policy: Literal["one_pre_action_transient_retry_only"] = (
        "one_pre_action_transient_retry_only"
    )
    timeout_or_malformed_output_counts_as_invalid: Literal[True] = True
    model_reroute_fails_closed: Literal[True] = True
    version_or_binary_drift_fails_closed: Literal[True] = True
    deterministic_presentation_cue_fails_closed: Literal[True] = True
    no_comparison_if_instrument_invalid: Literal[True] = True

    @field_validator("required_language_phenomena")
    @classmethod
    def language_phenomena_are_complete(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        expected = (
            "acronym_or_shorthand",
            "ambiguous_correction",
            "exact_revocation",
            "implicit_preference",
            "misspelling_or_bad_grammar",
            "narrow_context_exception",
            "one_off_request_near_miss",
            "quoted_untrusted_instruction",
        )
        if value != expected:
            raise ValueError("v2.1 requires the complete ordered language-phenomena set")
        return value


class PersonaCalibrationReport(FrozenModel):
    """Raw-free deterministic proof that the hardened packet boundaries behave as specified."""

    report_version: Literal["2.1.0"] = "2.1.0"
    evidence_class: Literal["disposable_instrument_calibration"] = (
        "disposable_instrument_calibration"
    )
    checks: tuple[NonEmptyStr, ...]
    passed: bool
    counts_toward_product_evidence: Literal[False] = False
    counts_toward_ordinary_use_gate: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def check_set_is_exact(self) -> Self:
        if self.checks != tuple(sorted(set(self.checks))):
            raise ValueError("calibration checks must be sorted and unique")
        if self.passed != bool(self.checks):
            raise ValueError("calibration passes only with a non-empty verified check set")
        return self


class PersonaV21ExecutionReceipt(FrozenModel):
    """Raw-free receipt for one isolated v2.1 role execution."""

    receipt_version: Literal["2.1.0"] = "2.1.0"
    execution_id: Identifier
    role: Literal[
        "profile_author",
        "profile_reviewer",
        "semantic_sensor",
        "guidance_judge",
        "guidance_adjudicator",
    ]
    persona_id: Identifier
    case_id: Identifier | None = None
    packet_digest: Sha256Digest
    model: Literal["gpt-5.6-luna", "gpt-5.6-sol"]
    reasoning_effort: Literal["medium", "xhigh", "max"]
    codex_cli_version: Literal["codex-cli 0.146.0"] = "codex-cli 0.146.0"
    codex_binary_digest: Literal[
        "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    ] = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
    trace_digest: Sha256Digest
    encrypted_trace_ref: Sha256Digest
    command_digest: Sha256Digest
    environment_digest: Sha256Digest
    fresh_ephemeral_session: Literal[True] = True
    exactly_one_persona: Literal[True] = True
    stage_bounded_evidence_only: Literal[True] = True
    hidden_oracle_visible: Literal[False] = False
    condition_mapping_visible: Literal[False] = False
    compiled_material_visible_to_static_role: Literal[False] = False
    host_home_visible: Literal[False] = False
    repository_visible: Literal[False] = False
    user_config_loaded: Literal[False] = False
    rules_loaded: Literal[False] = False
    memories_loaded: Literal[False] = False
    skills_loaded: Literal[False] = False
    plugins_loaded: Literal[False] = False
    mcp_loaded: Literal[False] = False
    prior_transcripts_loaded: Literal[False] = False
    tools_used: Literal[False] = False
    web_search_enabled: Literal[False] = False
    api_key_environment_present: Literal[False] = False
    saved_chatgpt_authentication: Literal[True] = True
    session_destroyed: Literal[True] = True
    external_validation_accessed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0

    @model_validator(mode="after")
    def role_configuration_is_exact(self) -> Self:
        expected = {
            "profile_author": ("gpt-5.6-sol", "xhigh", False),
            "profile_reviewer": ("gpt-5.6-sol", "xhigh", False),
            "semantic_sensor": ("gpt-5.6-luna", "medium", False),
            "guidance_judge": ("gpt-5.6-sol", "xhigh", True),
            "guidance_adjudicator": ("gpt-5.6-sol", "max", True),
        }
        model, effort, needs_case = expected[self.role]
        if (self.model, self.reasoning_effort) != (model, effort):
            raise ValueError("v2.1 receipt role used an unregistered model configuration")
        if (self.case_id is not None) is not needs_case:
            raise ValueError("v2.1 receipt case binding does not match its role")
        return self


class PersonaSensorReviewDecision(FrozenModel):
    """Raw-free deterministic review of one sensor decision."""

    decision_version: Literal["2.1.0"] = "2.1.0"
    batch_id: Identifier
    persona_id: Identifier
    turn: Annotated[int, Field(ge=1, le=11)]
    observation_digest: Sha256Digest
    interpretation_receipt_digest: Sha256Digest
    detection_digest: Sha256Digest
    approved: bool
    reasons: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @field_validator("reasons")
    @classmethod
    def reasons_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("sensor review reasons must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PersonaSensorReviewAdjudication(FrozenModel):
    """Deterministic downgrade when an approved lifecycle action has no active target."""

    adjudication_version: Literal["2.1.0"] = "2.1.0"
    adjudication_id: Identifier
    persona_id: Identifier
    turn: Annotated[int, Field(ge=1, le=11)]
    original_record_digest: Sha256Digest
    corrected_approved: Literal[False] = False
    reason: Literal["trusted lifecycle target was not active"] = (
        "trusted lifecycle target was not active"
    )

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PersonaV21SensorResult(FrozenModel):
    """One complete semantic session with reviewed records and a raw-free receipt."""

    result_version: Literal["2.1.0"] = "2.1.0"
    batch_id: Identifier
    persona_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    batch_digest: Sha256Digest
    records: Annotated[tuple[PersonaSensorRecord, ...], Field(min_length=3, max_length=4)]
    reviews: Annotated[tuple[PersonaSensorReviewDecision, ...], Field(min_length=3, max_length=4)]
    execution_receipt: PersonaV21ExecutionReceipt

    @model_validator(mode="after")
    def bindings_are_exact(self) -> Self:
        expected_turns = {
            1: tuple(range(1, 4)),
            2: tuple(range(4, 8)),
            3: tuple(range(8, 12)),
        }[self.stage]
        if tuple(item.turn for item in self.records) != expected_turns:
            raise ValueError("sensor result records do not match the exact stage segment")
        if tuple(item.turn for item in self.reviews) != expected_turns:
            raise ValueError("sensor result reviews do not match the exact stage segment")
        if any(item.persona_id != self.persona_id for item in self.records):
            raise ValueError("sensor result records crossed personas")
        if any(
            item.persona_id != self.persona_id or item.batch_id != self.batch_id
            for item in self.reviews
        ):
            raise ValueError("sensor result reviews crossed batch or persona boundaries")
        if self.execution_receipt.role != "semantic_sensor":
            raise ValueError("sensor result requires one semantic-sensor receipt")
        if self.execution_receipt.persona_id != self.persona_id:
            raise ValueError("sensor result receipt crossed personas")
        for record, review in zip(self.records, self.reviews, strict=True):
            if (
                record.observation_digest != review.observation_digest
                or record.interpretation_receipt_digest != review.interpretation_receipt_digest
                or record.detection_digest != review.detection_digest
                or record.approved != review.approved
                or (
                    record.review_receipt_digest
                    != (review.content_digest if review.approved else None)
                )
            ):
                raise ValueError("sensor record and deterministic review lineage drifted")
        return self


def adjudicate_inactive_lifecycle_targets(
    records: tuple[PersonaSensorRecord, ...],
) -> tuple[tuple[PersonaSensorRecord, ...], tuple[PersonaSensorReviewAdjudication, ...]]:
    """Downgrade, but never upgrade, approved lifecycle actions targeting no active claim."""

    turns = tuple(item.turn for item in records)
    if turns != tuple(sorted(set(turns))):
        raise ValueError("sensor adjudication requires chronological unique records")
    active: set[str] = set()
    effective: list[PersonaSensorRecord] = []
    adjudications: list[PersonaSensorReviewAdjudication] = []
    for record in records:
        corrected = record
        target_required = record.signal_kind is FeedbackSignalKind.REVOCATION or (
            record.transition_intent is SemanticTransitionIntent.CORRECTION
        )
        if record.approved and target_required and record.affected_claim_id not in active:
            original_digest = canonical_digest(record)
            adjudications.append(
                PersonaSensorReviewAdjudication(
                    adjudication_id=(
                        "sensor-adjudication-" + original_digest.removeprefix("sha256:")[:24]
                    ),
                    persona_id=record.persona_id,
                    turn=record.turn,
                    original_record_digest=original_digest,
                )
            )
            corrected = record.model_copy(update={"approved": False, "review_receipt_digest": None})
        if corrected.approved and corrected.signal_kind is not None:
            if target_required:
                target = cast(str, corrected.affected_claim_id)
                active.remove(target)
            if corrected.signal_kind is not FeedbackSignalKind.REVOCATION:
                active.add(cast(str, corrected.claim_id))
        effective.append(corrected)
    return tuple(effective), tuple(adjudications)


class PersonaV21Alternative(FrozenModel):
    alternative_id: Identifier
    content: NonEmptyStr


class PersonaV21JudgePacket(FrozenModel):
    """Guidance-only blind packet; internal learning correctness is scored deterministically."""

    packet_version: Literal["2.1.0"] = "2.1.0"
    packet_id: Identifier
    case: PersonaPublicCase
    evidence: PersonaStageEvidence
    replicate: Literal[1, 2, 3]
    alternatives: Annotated[
        tuple[PersonaV21Alternative, PersonaV21Alternative], Field(min_length=2)
    ]
    condition_mapping_withheld: Literal[True] = True
    expected_answers_withheld: Literal[True] = True
    prior_judgments_visible: Literal[False] = False

    @model_validator(mode="after")
    def packet_is_one_persona_and_one_stage(self) -> Self:
        if self.case.persona_id != self.evidence.persona_id:
            raise ValueError("judge packet crossed personas")
        if self.case.stage != self.evidence.stage:
            raise ValueError("judge packet crossed evidence stages")
        if len({item.alternative_id for item in self.alternatives}) != 2:
            raise ValueError("judge alternatives must be distinct")
        audit_public_payload(self)
        return self


class PersonaV21ModelJudgeDecision(FrozenModel):
    preference: PersonaPreference
    rationale: Annotated[str, Field(min_length=20, max_length=1500)]
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]


class PersonaV21JudgeDecision(FrozenModel):
    decision_version: Literal["2.1.0"] = "2.1.0"
    packet_id: Identifier
    case_id: Identifier
    ordered_alternative_ids: Annotated[tuple[Identifier, Identifier], Field(min_length=2)]
    preference: PersonaPreference
    rationale: Annotated[str, Field(min_length=20, max_length=1500)]
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]

    @property
    def preferred_alternative_id(self) -> Identifier | None:
        return {
            PersonaPreference.FIRST: self.ordered_alternative_ids[0],
            PersonaPreference.SECOND: self.ordered_alternative_ids[1],
            PersonaPreference.TIE: None,
        }[self.preference]


class PersonaGuidanceOutcome(FrozenModel):
    case_id: Identifier
    independent_agreement: bool
    adjudicated: bool
    resolved_source: PersonaMaterialSource | None
    resolved_tie: bool
    unresolved: bool

    @model_validator(mode="after")
    def resolution_is_exclusive(self) -> Self:
        states = sum((self.resolved_source is not None, self.resolved_tie, self.unresolved))
        if states != 1:
            raise ValueError("guidance outcome requires exactly one resolution state")
        if self.adjudicated is self.independent_agreement:
            raise ValueError("guidance adjudication must be the inverse of independent agreement")
        return self


class PersonaV21EvaluationReport(FrozenModel):
    report_version: Literal["2.1.0"] = "2.1.0"
    benchmark_id: Literal["temper-6a2l-persona-evaluation-v2.1"] = (
        "temper-6a2l-persona-evaluation-v2.1"
    )
    case_count: Literal[24] = 24
    compiled_objective_exact_rate: float = Field(ge=0, le=1)
    static_objective_exact_rate: float = Field(ge=0, le=1)
    guidance_agreement_rate: float = Field(ge=0, le=1)
    guidance_adjudication_rate: float = Field(ge=0, le=1)
    guidance_unresolved_rate: float = Field(ge=0, le=1)
    first_position_selection_rate: float = Field(ge=0, le=1)
    sentinel_accuracy: float = Field(ge=0, le=1)
    false_activation_count: int = Field(ge=0)
    lifecycle_leak_count: int = Field(ge=0)
    compiled_guidance_wins: int = Field(ge=0, le=24)
    static_guidance_wins: int = Field(ge=0, le=24)
    resolved_guidance_ties: int = Field(ge=0, le=24)
    outcomes: Annotated[tuple[PersonaGuidanceOutcome, ...], Field(min_length=24, max_length=24)]
    instrument_valid: bool
    interpretation: Literal[
        "instrument_failure",
        "compiled_negative",
        "compiled_directional_tie",
        "compiled_directional_positive",
    ]
    counts_toward_ordinary_use_gate: Literal[False] = False
    cross_agent_transfer_established: Literal[False] = False
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def invalid_instrument_suppresses_comparison(self) -> Self:
        if len({item.case_id for item in self.outcomes}) != 24:
            raise ValueError("v2.1 report requires 24 unique guidance outcomes")
        if not self.instrument_valid and self.interpretation != "instrument_failure":
            raise ValueError("invalid v2.1 instrument cannot compare conditions")
        return self


class PersonaV21ObjectiveGateReport(FrozenModel):
    """Pre-guidance result that prevents comparison when learning-state recovery is invalid."""

    report_version: Literal["2.1.0"] = "2.1.0"
    benchmark_id: Literal["temper-6a2l-persona-evaluation-v2.1"] = (
        "temper-6a2l-persona-evaluation-v2.1"
    )
    status: Literal["comparison_permitted", "stopped_at_objective_gate"]
    case_count: Literal[24] = 24
    objective_exact_rate_minimum: float = Field(default=0.75, ge=0, le=1)
    compiled_exact_count: Annotated[int, Field(ge=0, le=24)]
    static_exact_count: Annotated[int, Field(ge=0, le=24)]
    compiled_objective_exact_rate: float = Field(ge=0, le=1)
    static_objective_exact_rate: float = Field(ge=0, le=1)
    nonempty_expected_case_count: Annotated[int, Field(ge=0, le=24)]
    compiled_nonempty_exact_count: Annotated[int, Field(ge=0, le=24)]
    static_nonempty_exact_count: Annotated[int, Field(ge=0, le=24)]
    empty_expected_case_count: Annotated[int, Field(ge=0, le=24)]
    compiled_empty_exact_count: Annotated[int, Field(ge=0, le=24)]
    static_empty_exact_count: Annotated[int, Field(ge=0, le=24)]
    compiled_material_claim_count: int = Field(ge=0)
    reviewed_static_claim_count: int = Field(ge=0)
    delivered_static_claim_count: int = Field(ge=0)
    static_scope_transport_valid: bool
    compiled_gate_passed: bool
    static_gate_passed: bool
    comparison_permitted: bool
    instrument_valid: bool
    interpretation: Literal["instrument_failure", "objective_gate_passed"]
    guidance_sessions_executed: Literal[0] = 0
    diagnostic_codes: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    counts_toward_ordinary_use_gate: Literal[False] = False
    cross_agent_transfer_established: Literal[False] = False
    external_validation_accessed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0

    @field_validator("diagnostic_codes")
    @classmethod
    def diagnostics_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("objective-gate diagnostics must be sorted and unique")
        return value

    @model_validator(mode="after")
    def gate_arithmetic_is_exact(self) -> Self:
        if self.objective_exact_rate_minimum != 0.75:
            raise ValueError("v2.1 objective-gate minimum must remain frozen at 0.75")
        if self.nonempty_expected_case_count + self.empty_expected_case_count != self.case_count:
            raise ValueError("objective-gate expected-state groups must cover every case")
        if self.compiled_nonempty_exact_count + self.compiled_empty_exact_count != (
            self.compiled_exact_count
        ):
            raise ValueError("compiled objective-gate subgroup counts drifted")
        if self.static_nonempty_exact_count + self.static_empty_exact_count != (
            self.static_exact_count
        ):
            raise ValueError("static objective-gate subgroup counts drifted")
        if self.compiled_objective_exact_rate != self.compiled_exact_count / self.case_count:
            raise ValueError("compiled objective-gate rate drifted")
        if self.static_objective_exact_rate != self.static_exact_count / self.case_count:
            raise ValueError("static objective-gate rate drifted")
        compiled_passed = self.compiled_objective_exact_rate >= self.objective_exact_rate_minimum
        static_passed = self.static_objective_exact_rate >= self.objective_exact_rate_minimum
        comparison_permitted = compiled_passed and static_passed
        if (
            self.compiled_gate_passed != compiled_passed
            or self.static_gate_passed != static_passed
            or self.comparison_permitted != comparison_permitted
            or self.instrument_valid != comparison_permitted
        ):
            raise ValueError("objective-gate decision does not match its frozen rates")
        expected_status = (
            "comparison_permitted" if comparison_permitted else "stopped_at_objective_gate"
        )
        if self.status != expected_status:
            raise ValueError("objective-gate status does not match its decision")
        expected_interpretation = (
            "objective_gate_passed" if comparison_permitted else "instrument_failure"
        )
        if self.interpretation != expected_interpretation:
            raise ValueError("objective-gate interpretation does not match its decision")
        return self

    def require_comparison_permitted(self) -> None:
        """Fail closed before any guidance session when either objective lane is invalid."""

        if not self.comparison_permitted:
            raise RuntimeError("v2.1 objective gate failed; guidance comparison is prohibited")


def build_stage_evidence(history: PersonaEvidenceHistory, stage: int) -> PersonaStageEvidence:
    """Strip all labels and all evidence later than the requested checkpoint."""

    if stage not in range(1, 5):
        raise ValueError("persona evidence stage must be between one and four")
    checkpoint = _CHECKPOINTS[stage - 1]
    return PersonaStageEvidence(
        persona_id=history.persona_id,
        stage=stage,
        checkpoint_turn=cast(Literal[3, 7, 11, 15], checkpoint),
        messages=tuple(
            PersonaEvidenceMessage(turn=item.turn, message=item.message)
            for item in history.interactions
            if item.turn <= checkpoint
        ),
    )


def build_profile_author_packet(
    history: PersonaEvidenceHistory,
    stage: int,
) -> PersonaProfileAuthorPacket:
    packet = PersonaProfileAuthorPacket(
        persona_id=history.persona_id,
        evidence=build_stage_evidence(history, stage),
    )
    audit_public_payload(packet)
    return packet


def build_profile_review_packet(
    author_packet: PersonaProfileAuthorPacket,
    draft: PersonaModelProfileOutput,
) -> PersonaProfileReviewPacket:
    packet = PersonaProfileReviewPacket(
        persona_id=author_packet.persona_id,
        evidence=author_packet.evidence,
        draft=draft,
    )
    audit_public_payload(packet)
    return packet


def _claim_id(*, persona_id: str, stage: int, claim: PersonaModelProfileClaim) -> Identifier:
    digest = canonical_digest(
        {
            "persona_id": persona_id,
            "stage": stage,
            "claim": claim.model_dump(mode="json", round_trip=True),
        }
    ).removeprefix("sha256:")
    return f"claim-{digest[:24]}"


def _message_digest(message: PersonaEvidenceMessage) -> Sha256Digest:
    return canonical_digest(message)


def render_neutral_guidance(claims: tuple[PersonaMaterialClaim, ...]) -> NonEmptyStr:
    """Render both conditions through one presentation channel without provenance cues."""

    applicable = tuple(sorted(claims, key=lambda item: (item.source_turns, item.statement)))
    if not applicable:
        return "No durable instruction is applicable to this scenario."
    return "\n".join(f"- {item.statement}" for item in applicable)


def bind_reviewed_profile_material(
    *,
    case: PersonaPublicCase,
    evidence: PersonaStageEvidence,
    reviewed: PersonaModelProfileOutput,
) -> PersonaMaterialSnapshot:
    """Bind an identity-free independently reviewed profile to exact visible evidence."""

    if case.persona_id != evidence.persona_id or case.stage != evidence.stage:
        raise ValueError("profile material crossed persona or stage")
    snapshot = reviewed.snapshot
    if snapshot.stage != case.stage:
        raise ValueError("reviewed profile output crossed stages")
    visible = {item.turn: item for item in evidence.messages}
    claims: list[PersonaMaterialClaim] = []
    for proposal in snapshot.claims:
        if any(turn not in visible for turn in proposal.source_turns):
            raise ValueError("reviewed profile cited hidden or future evidence")
        claims.append(
            PersonaMaterialClaim(
                claim_id=_claim_id(persona_id=case.persona_id, stage=case.stage, claim=proposal),
                statement=proposal.statement,
                route=proposal.route,
                scope=proposal.scope,
                source_turns=proposal.source_turns,
                evidence_digests=tuple(
                    _message_digest(visible[turn]) for turn in proposal.source_turns
                ),
            )
        )
    applicable = tuple(item for item in claims if scope_is_within(case.current_scope, item.scope))
    return PersonaMaterialSnapshot(
        case_id=case.case_id,
        persona_id=case.persona_id,
        source=PersonaMaterialSource.STATIC,
        claims=applicable,
        target_guidance=render_neutral_guidance(applicable),
        evidence_checkpoint_digest=evidence.content_digest,
        independently_reviewed=True,
    )


def bind_sensor_record(
    *,
    persona_id: Identifier,
    turn: int,
    evidence: PersonaEvidenceMessage,
    observation: InteractionObservation,
    interpretation: SemanticFeedbackInterpretation,
    detection: DetectedFeedback,
    approved: bool,
    review_receipt_digest: Sha256Digest | None,
) -> PersonaSensorRecord:
    """Bind real semantic output and deterministic detection to one exact evidence turn."""

    if evidence.turn != turn or evidence.message != observation.text:
        raise ValueError("sensor observation does not match visible evidence")
    if (
        interpretation.observation_id != observation.observation_id
        or interpretation.observation_digest != observation.content_digest
        or detection.observation_digest != observation.content_digest
    ):
        raise ValueError("sensor lineage does not bind the exact observation")
    if detection.detector_mode is not FeedbackDetectorMode.REVIEW:
        raise ValueError("persona sensor construction must use review mode")
    if detection.interpreter_receipt_digest != interpretation.receipt.content_digest:
        raise ValueError("detector does not bind the semantic interpreter receipt")
    signal = None
    if detection.signal_kind is not None:
        matches = tuple(
            item
            for item in interpretation.signals
            if item.signal_kind is detection.signal_kind
            and item.normalized_behavior == detection.normalized_behavior
            and item.requested_route == detection.requested_route
        )
        if len(matches) != 1:
            raise ValueError("detector decision does not bind exactly one semantic signal")
        signal = matches[0]
    actionable = detection.disposition in {
        AutomationDisposition.PROMOTED,
        AutomationDisposition.REVIEW_REQUIRED,
        AutomationDisposition.REVOKED,
    }
    if approved and not actionable:
        raise ValueError("non-actionable semantic output cannot be approved")
    transition = (
        None
        if signal is None or signal.semantic_features is None
        else signal.semantic_features.transition_intent
    )
    return PersonaSensorRecord(
        persona_id=persona_id,
        turn=turn,
        observation_digest=observation.content_digest,
        interpretation_receipt_digest=interpretation.receipt.content_digest,
        detection_digest=detection.content_digest,
        claim_id=(
            None if detection.signal_kind is FeedbackSignalKind.REVOCATION else detection.claim_key
        ),
        signal_kind=detection.signal_kind,
        transition_intent=transition,
        statement=detection.normalized_behavior,
        route=detection.requested_route,
        scope=detection.scope,
        affected_claim_id=detection.affected_artifact_id,
        approved=approved,
        review_receipt_digest=review_receipt_digest,
    )


def compile_sensor_material(
    *,
    case: PersonaPublicCase,
    evidence: PersonaStageEvidence,
    records: tuple[PersonaSensorRecord, ...],
) -> PersonaMaterialSnapshot:
    """Apply approved semantic records in order, then project only applicable active claims."""

    if case.persona_id != evidence.persona_id or case.stage != evidence.stage:
        raise ValueError("compiled material crossed persona or stage")
    visible = {item.turn: item for item in evidence.messages}
    turns = tuple(item.turn for item in records)
    if turns != tuple(sorted(set(turns))):
        raise ValueError("sensor records must be chronological and unique by evidence turn")
    if any(item.persona_id != case.persona_id or item.turn not in visible for item in records):
        raise ValueError("sensor records crossed persona or stage-bounded evidence")
    active: dict[str, PersonaMaterialClaim] = {}
    for record in records:
        if not record.approved or record.signal_kind is None:
            continue
        if record.signal_kind is FeedbackSignalKind.REVOCATION:
            target = record.affected_claim_id
            if target is None or target not in active:
                raise ValueError("revocation does not bind one active claim")
            active.pop(target)
            continue
        if record.transition_intent is SemanticTransitionIntent.CORRECTION:
            target = record.affected_claim_id
            if target is None or target not in active:
                raise ValueError("correction does not bind one active claim")
            active.pop(target)
        if record.claim_id is None or record.statement is None or record.route is None:
            raise ValueError("approved content record lacks material fields")
        if record.claim_id in active:
            raise ValueError("semantic compilation produced a duplicate active claim")
        active[record.claim_id] = PersonaMaterialClaim(
            claim_id=record.claim_id,
            statement=record.statement,
            route=record.route,
            scope=record.scope,
            source_turns=(record.turn,),
            evidence_digests=(_message_digest(visible[record.turn]),),
            interpretation_receipt_digest=record.interpretation_receipt_digest,
            detection_digest=record.detection_digest,
        )
    applicable = tuple(
        sorted(
            (item for item in active.values() if scope_is_within(case.current_scope, item.scope)),
            key=lambda item: item.claim_id,
        )
    )
    return PersonaMaterialSnapshot(
        case_id=case.case_id,
        persona_id=case.persona_id,
        source=PersonaMaterialSource.COMPILED,
        claims=applicable,
        target_guidance=render_neutral_guidance(applicable),
        evidence_checkpoint_digest=evidence.content_digest,
        independently_reviewed=False,
    )


def score_objective_state(
    material: PersonaMaterialSnapshot,
    oracle: PersonaHiddenOracle,
) -> PersonaObjectiveScore:
    """Score activation, route, scope, lifecycle, and lineage without an AI preference vote."""

    if material.case_id != oracle.case_id or material.persona_id != oracle.persona_id:
        raise ValueError("objective score crossed its hidden oracle binding")
    expected = {item.source_turn: item for item in oracle.active_claims}
    actual: dict[int, PersonaMaterialClaim] = {}
    duplicate_turns: set[int] = set()
    for claim in material.claims:
        governing_turn = claim.source_turns[-1]
        if governing_turn in actual:
            duplicate_turns.add(governing_turn)
        actual[governing_turn] = claim
    expected_turns = set(expected)
    actual_turns = set(actual)
    missing = tuple(sorted(expected_turns - actual_turns))
    unexpected = tuple(sorted((actual_turns - expected_turns) | duplicate_turns))
    forbidden = tuple(sorted(actual_turns & set(oracle.forbidden_source_turns)))
    route_mismatch = tuple(
        sorted(
            turn
            for turn in expected_turns & actual_turns
            if actual[turn].route is not expected[turn].route
        )
    )
    scope_mismatch = tuple(
        sorted(
            turn
            for turn in expected_turns & actual_turns
            if actual[turn].scope != expected[turn].scope
        )
    )
    correct = len(expected_turns - set(missing) - set(route_mismatch) - set(scope_mismatch))
    lineage_complete = all(
        len(item.source_turns) == len(item.evidence_digests)
        and all(value.startswith("sha256:") for value in item.evidence_digests)
        and (
            material.source is PersonaMaterialSource.STATIC
            or (
                item.interpretation_receipt_digest is not None and item.detection_digest is not None
            )
        )
        for item in material.claims
    )
    exact = (
        not any((missing, unexpected, forbidden, route_mismatch, scope_mismatch))
        and lineage_complete
    )
    return PersonaObjectiveScore(
        case_id=material.case_id,
        source=material.source,
        expected_count=len(expected),
        correct_count=correct,
        missing_source_turns=missing,
        unexpected_source_turns=unexpected,
        forbidden_source_turns=forbidden,
        route_mismatch_source_turns=route_mismatch,
        scope_mismatch_source_turns=scope_mismatch,
        lineage_complete=lineage_complete,
        exact=exact,
    )


def _blind_id(seed: bytes, label: str, prefix: str) -> Identifier:
    if len(seed) != 32:
        raise ValueError("persona randomization seed must be 32 bytes")
    digest = hmac.new(seed, label.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}-{digest[:24]}"


def build_v21_judge_packet(
    *,
    seed: bytes,
    case: PersonaPublicCase,
    evidence: PersonaStageEvidence,
    compiled: PersonaMaterialSnapshot,
    static: PersonaMaterialSnapshot,
    replicate: Literal[1, 2, 3],
) -> tuple[PersonaV21JudgePacket, dict[Identifier, PersonaMaterialSource]]:
    """Create a guidance-only counterbalanced packet after objective state scoring freezes."""

    if {compiled.case_id, static.case_id} != {case.case_id}:
        raise ValueError("judge materials do not bind the public case")
    if {compiled.persona_id, static.persona_id} != {case.persona_id}:
        raise ValueError("judge materials do not bind the public persona")
    if {
        compiled.evidence_checkpoint_digest,
        static.evidence_checkpoint_digest,
    } != {evidence.content_digest}:
        raise ValueError("judge materials do not bind the visible evidence checkpoint")
    if compiled.source is not PersonaMaterialSource.COMPILED:
        raise ValueError("compiled judge material has the wrong source")
    if static.source is not PersonaMaterialSource.STATIC:
        raise ValueError("static judge material has the wrong source")
    alternatives = [
        PersonaV21Alternative(
            alternative_id=_blind_id(seed, f"{case.case_id}:compiled", "alternative"),
            content=compiled.target_guidance,
        ),
        PersonaV21Alternative(
            alternative_id=_blind_id(seed, f"{case.case_id}:static", "alternative"),
            content=static.target_guidance,
        ),
    ]
    mapping = {
        alternatives[0].alternative_id: PersonaMaterialSource.COMPILED,
        alternatives[1].alternative_id: PersonaMaterialSource.STATIC,
    }
    reverse = replicate == 2 or (
        replicate == 3 and int(hashlib.sha256(case.case_id.encode()).hexdigest(), 16) % 2
    )
    if reverse:
        alternatives.reverse()
    packet = PersonaV21JudgePacket(
        packet_id=_blind_id(seed, f"{case.case_id}:replicate:{replicate}", "packet"),
        case=case,
        evidence=evidence,
        replicate=replicate,
        alternatives=(alternatives[0], alternatives[1]),
    )
    return packet, mapping


def bind_v21_judge_decision(
    packet: PersonaV21JudgePacket,
    model: PersonaV21ModelJudgeDecision,
) -> PersonaV21JudgeDecision:
    """Bind the model's position-only vote to trusted packet and alternative identities."""

    return PersonaV21JudgeDecision(
        packet_id=packet.packet_id,
        case_id=packet.case.case_id,
        ordered_alternative_ids=(
            packet.alternatives[0].alternative_id,
            packet.alternatives[1].alternative_id,
        ),
        preference=model.preference,
        rationale=model.rationale,
        limitations=model.limitations,
    )


def _mapped_vote(
    decision: PersonaV21JudgeDecision,
    mapping: dict[Identifier, PersonaMaterialSource],
) -> PersonaMaterialSource | None:
    if set(decision.ordered_alternative_ids) != set(mapping):
        raise ValueError("judge decision does not bind the private condition mapping")
    preferred = decision.preferred_alternative_id
    if preferred is None:
        return None
    try:
        return mapping[preferred]
    except KeyError as error:
        raise ValueError("judge decision is absent from the private condition mapping") from error


def resolve_v21_guidance(
    *,
    first: PersonaV21JudgeDecision,
    second: PersonaV21JudgeDecision,
    mapping: dict[Identifier, PersonaMaterialSource],
    adjudicator: PersonaV21JudgeDecision | None = None,
) -> PersonaGuidanceOutcome:
    """Resolve guidance votes without exposing condition identities to any model role."""

    if first.case_id != second.case_id or (
        adjudicator is not None and adjudicator.case_id != first.case_id
    ):
        raise ValueError("guidance decisions crossed cases")
    first_vote = _mapped_vote(first, mapping)
    second_vote = _mapped_vote(second, mapping)
    agreed = first_vote == second_vote
    if agreed and adjudicator is not None:
        raise ValueError("agreed guidance decisions must not be adjudicated")
    if not agreed and adjudicator is None:
        raise ValueError("disputed guidance decisions require one fresh adjudicator")
    votes: tuple[PersonaMaterialSource | None, ...]
    if agreed:
        votes = (first_vote, second_vote)
    else:
        adjudicator_vote = _mapped_vote(cast(PersonaV21JudgeDecision, adjudicator), mapping)
        votes = (first_vote, second_vote, adjudicator_vote)
    counts = Counter(votes)
    highest = max(counts.values())
    leaders = tuple(item for item, count in counts.items() if count == highest)
    unresolved = len(leaders) != 1 or highest < 2
    winner = None if unresolved else leaders[0]
    return PersonaGuidanceOutcome(
        case_id=first.case_id,
        independent_agreement=agreed,
        adjudicated=not agreed,
        resolved_source=(winner if isinstance(winner, PersonaMaterialSource) else None),
        resolved_tie=winner is None and not unresolved,
        unresolved=unresolved,
    )


def build_v21_evaluation_report(
    *,
    protocol: PersonaV21Protocol,
    compiled_scores: tuple[PersonaObjectiveScore, ...],
    static_scores: tuple[PersonaObjectiveScore, ...],
    outcomes: tuple[PersonaGuidanceOutcome, ...],
    independent_decisions: tuple[PersonaV21JudgeDecision, ...],
    sentinel_case_ids: tuple[Identifier, ...],
) -> PersonaV21EvaluationReport:
    """Apply frozen validity gates before exposing any condition-level interpretation."""

    if not (
        len(compiled_scores) == len(static_scores) == len(outcomes) == protocol.case_count
        and len(independent_decisions) == protocol.case_count * 2
    ):
        raise ValueError("v2.1 evaluation inputs do not match the frozen sample size")
    if any(item.source is not PersonaMaterialSource.COMPILED for item in compiled_scores):
        raise ValueError("compiled objective scores contain another material source")
    if any(item.source is not PersonaMaterialSource.STATIC for item in static_scores):
        raise ValueError("static objective scores contain another material source")
    outcome_by_case = {item.case_id: item for item in outcomes}
    compiled_score_by_case = {item.case_id: item for item in compiled_scores}
    static_score_by_case = {item.case_id: item for item in static_scores}
    if not (
        len(outcome_by_case)
        == len(compiled_score_by_case)
        == len(static_score_by_case)
        == protocol.case_count
        and set(outcome_by_case) == set(compiled_score_by_case) == set(static_score_by_case)
    ):
        raise ValueError("v2.1 evaluation case bindings are incomplete, duplicated, or crossed")
    compiled_rate = sum(item.exact for item in compiled_scores) / protocol.case_count
    static_rate = sum(item.exact for item in static_scores) / protocol.case_count
    agreement_rate = sum(item.independent_agreement for item in outcomes) / protocol.case_count
    adjudication_rate = sum(item.adjudicated for item in outcomes) / protocol.case_count
    unresolved_rate = sum(item.unresolved for item in outcomes) / protocol.case_count
    first_position_rate = sum(
        item.preference is PersonaPreference.FIRST for item in independent_decisions
    ) / len(independent_decisions)
    sentinel_set = set(sentinel_case_ids)
    if not sentinel_set or not sentinel_set <= set(outcome_by_case):
        raise ValueError("sentinel case IDs do not bind the completed outcomes")
    sentinel_accuracy = sum(
        compiled_score_by_case[case_id].exact and static_score_by_case[case_id].exact
        for case_id in sentinel_set
    ) / len(sentinel_set)
    false_activations = sum(
        bool(item.unexpected_source_turns)
        for item in compiled_scores
        if item.case_id in sentinel_set
    )
    lifecycle_leaks = sum(bool(item.forbidden_source_turns) for item in compiled_scores)
    valid = (
        compiled_rate >= protocol.objective_exact_rate_minimum
        and static_rate >= protocol.static_objective_exact_rate_minimum
        and agreement_rate >= protocol.guidance_agreement_rate_minimum
        and adjudication_rate <= protocol.guidance_adjudication_rate_maximum
        and unresolved_rate <= protocol.guidance_unresolved_rate_maximum
        and sentinel_accuracy >= protocol.sentinel_accuracy_minimum
        and false_activations <= protocol.false_activation_maximum
        and lifecycle_leaks <= protocol.lifecycle_leak_maximum
    )
    compiled_wins = sum(item.resolved_source is PersonaMaterialSource.COMPILED for item in outcomes)
    static_wins = sum(item.resolved_source is PersonaMaterialSource.STATIC for item in outcomes)
    ties = sum(item.resolved_tie for item in outcomes)
    if not valid:
        interpretation: Literal[
            "instrument_failure",
            "compiled_negative",
            "compiled_directional_tie",
            "compiled_directional_positive",
        ] = "instrument_failure"
    elif compiled_wins > static_wins:
        interpretation = "compiled_directional_positive"
    elif compiled_wins == static_wins:
        interpretation = "compiled_directional_tie"
    else:
        interpretation = "compiled_negative"
    return PersonaV21EvaluationReport(
        compiled_objective_exact_rate=compiled_rate,
        static_objective_exact_rate=static_rate,
        guidance_agreement_rate=agreement_rate,
        guidance_adjudication_rate=adjudication_rate,
        guidance_unresolved_rate=unresolved_rate,
        first_position_selection_rate=first_position_rate,
        sentinel_accuracy=sentinel_accuracy,
        false_activation_count=false_activations,
        lifecycle_leak_count=lifecycle_leaks,
        compiled_guidance_wins=compiled_wins,
        static_guidance_wins=static_wins,
        resolved_guidance_ties=ties,
        outcomes=outcomes,
        instrument_valid=valid,
        interpretation=interpretation,
    )


def audit_public_payload(value: FrozenModel | dict[str, object]) -> None:
    """Fail closed on answer keys, future summaries, or deterministic condition cues."""

    payload = (
        value.model_dump(mode="json", round_trip=True) if isinstance(value, FrozenModel) else value
    )

    def visit(node: object) -> None:
        if isinstance(node, dict):
            leaked = set(node) & _FORBIDDEN_PUBLIC_KEYS
            if leaked:
                raise ValueError(
                    "public persona packet contains hidden keys: " + ", ".join(sorted(leaked))
                )
            for item in node.values():
                visit(item)
        elif isinstance(node, list | tuple):
            for item in node:
                visit(item)

    visit(payload)
    rendered = canonical_json(payload).casefold()
    leaked_cues = tuple(item for item in _FORBIDDEN_PRESENTATION_CUES if item in rendered)
    if leaked_cues:
        raise ValueError("public persona packet reveals a condition presentation cue")


def persona_v21_profile_output_schema() -> dict[str, object]:
    """Return a closed model-facing schema for author and reviewer outputs."""

    schema = PersonaModelProfileOutput.model_json_schema()

    def close(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for item in node.values():
                close(item)
        elif isinstance(node, list):
            for item in node:
                close(item)

    close(schema)
    return schema


def persona_v21_judge_output_schema() -> dict[str, object]:
    """Return a closed identity-free schema for a guidance-quality vote."""

    schema = PersonaV21ModelJudgeDecision.model_json_schema()

    def close(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for item in node.values():
                close(item)
        elif isinstance(node, list):
            for item in node:
                close(item)

    close(schema)
    return schema
