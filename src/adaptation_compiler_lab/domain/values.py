"""Reusable immutable value objects shared by top-level records."""

import hashlib
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain.base import (
    ActorRef,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import (
    ActorKind,
    ApprovalDecision,
    ArtifactKind,
    ArtifactRoute,
    AssertionStatus,
    AuthorityClass,
    ClaimType,
    ConflictResolution,
    EvaluationResult,
    LossMateriality,
    Partition,
    PermittedUse,
    PrivacyReviewState,
    ScoringType,
    SensitivityClass,
)
from adaptation_compiler_lab.domain.references import (
    AnyRecordRef,
    ArtifactRef,
    EvaluationCaseRef,
    EvidenceRef,
    ExactRecordRef,
)


def strings_are_sorted_unique(values: tuple[str, ...]) -> bool:
    return list(values) == sorted(set(values))


def record_ref_key(reference: AnyRecordRef) -> tuple[str, str, str, str]:
    return (
        reference.record_type.value,
        reference.record_id,
        reference.record_version,
        reference.content_digest or "",
    )


def refs_are_sorted_unique(values: tuple[AnyRecordRef, ...]) -> bool:
    keys = [record_ref_key(value) for value in values]
    return keys == sorted(set(keys))


IdentifierTuple = tuple[Identifier, ...]
NonEmptyIdentifierTuple = Annotated[IdentifierTuple, Field(min_length=1)]
EvidenceRefTuple = tuple[EvidenceRef, ...]
NonEmptyEvidenceRefTuple = Annotated[EvidenceRefTuple, Field(min_length=1)]


class Scope(FrozenModel):
    """Machine-comparable applicability bounds.

    Empty optional dimensions mean unconstrained. Subjects are never unconstrained in this
    single-user prototype. A narrower scope may restrict a dimension, add exclusions or
    activation conditions, and shrink the validity window.
    """

    subject_ids: NonEmptyIdentifierTuple
    workspace_ids: IdentifierTuple = ()
    project_ids: IdentifierTuple = ()
    repository_ids: IdentifierTuple = ()
    task_classes: IdentifierTuple = ()
    target_families: IdentifierTuple = ()
    environment_ids: IdentifierTuple = ()
    activation_conditions: tuple[NonEmptyStr, ...] = ()
    exclusions: tuple[NonEmptyStr, ...] = ()
    valid_from: UtcDateTime | None = None
    valid_until: UtcDateTime | None = None

    @field_validator(
        "subject_ids",
        "workspace_ids",
        "project_ids",
        "repository_ids",
        "task_classes",
        "target_families",
        "environment_ids",
        "activation_conditions",
        "exclusions",
    )
    @classmethod
    def require_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("scope values must be sorted and unique")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "Scope":
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_from >= self.valid_until
        ):
            raise ValueError("valid_from must be earlier than valid_until")
        return self


def scope_is_within(child: Scope, parent: Scope) -> bool:
    """Return whether ``child`` is equal to or narrower than ``parent``."""

    dimensions = (
        "subject_ids",
        "workspace_ids",
        "project_ids",
        "repository_ids",
        "task_classes",
        "target_families",
        "environment_ids",
    )
    for name in dimensions:
        parent_values = set(getattr(parent, name))
        child_values = set(getattr(child, name))
        if parent_values and (not child_values or not child_values <= parent_values):
            return False
    if not set(parent.exclusions) <= set(child.exclusions):
        return False
    if not set(parent.activation_conditions) <= set(child.activation_conditions):
        return False
    if parent.valid_from is not None and (
        child.valid_from is None or child.valid_from < parent.valid_from
    ):
        return False
    return not (
        parent.valid_until is not None
        and (child.valid_until is None or child.valid_until > parent.valid_until)
    )


class PrivacyContext(FrozenModel):
    sensitivity: SensitivityClass
    consent_basis: Identifier
    consent_basis_refs: tuple[Identifier, ...] = Field(
        default=(),
        exclude_if=lambda value: not value,
    )
    permitted_uses: Annotated[tuple[PermittedUse, ...], Field(min_length=1)]
    review_state: PrivacyReviewState = PrivacyReviewState.PENDING
    reviewed_by: ActorRef | None = None
    reviewed_at: UtcDateTime | None = None
    notes: NonEmptyStr | None = None

    @field_validator("permitted_uses")
    @classmethod
    def uses_are_sorted_unique(cls, value: tuple[PermittedUse, ...]) -> tuple[PermittedUse, ...]:
        raw = tuple(item.value for item in value)
        if not strings_are_sorted_unique(raw):
            raise ValueError("permitted uses must be sorted and unique")
        return value

    @field_validator("consent_basis_refs")
    @classmethod
    def consent_refs_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("consent basis references must be sorted and unique")
        return value

    @model_validator(mode="after")
    def review_is_attributable(self) -> "PrivacyContext":
        if self.consent_basis_refs:
            if len(self.consent_basis_refs) < 2:
                raise ValueError("a consent set must contain at least two exact bases")
            if self.consent_basis != consent_set_identifier(self.consent_basis_refs):
                raise ValueError("aggregate consent basis does not match its exact basis set")
        has_review = self.reviewed_by is not None or self.reviewed_at is not None
        if self.review_state is PrivacyReviewState.PENDING and has_review:
            raise ValueError("pending privacy review cannot have reviewer metadata")
        if self.review_state is not PrivacyReviewState.PENDING:
            if self.reviewed_by is None or self.reviewed_at is None:
                raise ValueError("completed privacy review requires reviewer and timestamp")
            if self.reviewed_by.kind not in {ActorKind.USER, ActorKind.HUMAN_REVIEWER}:
                raise ValueError("privacy review must be attributable to a human")
        return self

    @property
    def effective_consent_bases(self) -> frozenset[str]:
        """Return the exact single basis or explicit aggregate basis members."""

        return frozenset(self.consent_basis_refs or (self.consent_basis,))


def consent_set_identifier(consent_bases: tuple[str, ...]) -> str:
    """Return a stable non-secret identifier for a sorted exact consent set."""

    encoded = b"adaptation-compiler-lab/consent-set/v1\x00" + b"\x00".join(
        item.encode("utf-8") for item in consent_bases
    )
    return f"consent-set-{hashlib.sha256(encoded).hexdigest()[:24]}"


class PayloadSpan(FrozenModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def end_follows_start(self) -> "PayloadSpan":
        if self.end <= self.start:
            raise ValueError("payload span end must exceed start")
        return self


class PayloadReference(FrozenModel):
    """Reference to bytes retained in the segregated evidence store."""

    locator: NonEmptyStr
    content_digest: Sha256Digest
    media_type: NonEmptyStr
    byte_length: int = Field(ge=0)
    span: PayloadSpan | None = None


class EnvironmentFact(FrozenModel):
    name: Identifier
    value: NonEmptyStr


class EnvironmentSnapshot(FrozenModel):
    environment_id: Identifier
    harness_version: SemVer
    repository_digest: Sha256Digest | None = None
    model_id: NonEmptyStr | Literal["unknown"] = "unknown"
    agent_version: NonEmptyStr | Literal["unknown"] = "unknown"
    tool_ids: IdentifierTuple = ()
    facts: tuple[EnvironmentFact, ...] = ()
    random_seed: int | Literal["unknown"] = "unknown"

    @field_validator("tool_ids")
    @classmethod
    def tools_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("tool identifiers must be sorted and unique")
        return value

    @field_validator("facts")
    @classmethod
    def facts_are_sorted_unique(
        cls, value: tuple[EnvironmentFact, ...]
    ) -> tuple[EnvironmentFact, ...]:
        names = tuple(item.name for item in value)
        if not strings_are_sorted_unique(names):
            raise ValueError("environment facts must have sorted unique names")
        return value


class SyntheticOrigin(FrozenModel):
    fixture_id: Identifier
    description: NonEmptyStr


class Transformation(FrozenModel):
    method: Identifier
    transformer_version: SemVer
    policy_version: SemVer
    actor: ActorRef
    transformed_at: UtcDateTime
    input_evidence_refs: NonEmptyEvidenceRefTuple

    @field_validator("input_evidence_refs")
    @classmethod
    def inputs_are_sorted_unique(cls, value: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("transformation inputs must be sorted and unique")
        return value


class EvidenceLinks(FrozenModel):
    """Direct evidence roles retained by every lesson and artifact."""

    supporting: NonEmptyEvidenceRefTuple
    contradicting: EvidenceRefTuple = ()
    scope_limiting: EvidenceRefTuple = ()
    review_complete: Literal[True] = True

    @field_validator("supporting", "contradicting", "scope_limiting")
    @classmethod
    def links_are_sorted_unique(cls, value: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("evidence links must be sorted and unique")
        return value


class ClaimAuthority(FrozenModel):
    """Claim-specific authority that a renderer must preserve without strengthening."""

    claim_type: ClaimType
    authority_class: AuthorityClass
    evidence_refs: NonEmptyEvidenceRefTuple

    @field_validator("evidence_refs")
    @classmethod
    def evidence_is_sorted_unique(cls, value: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("claim-authority evidence must be sorted and unique")
        return value


class ClaimAuthoritySet(FrozenModel):
    entries: Annotated[tuple[ClaimAuthority, ...], Field(min_length=1)]

    @field_validator("entries")
    @classmethod
    def entries_are_sorted_unique(
        cls, value: tuple[ClaimAuthority, ...]
    ) -> tuple[ClaimAuthority, ...]:
        keys = tuple(
            (
                item.claim_type.value,
                item.authority_class.value,
                tuple(record_ref_key(reference) for reference in item.evidence_refs),
            )
            for item in value
        )
        if list(keys) != sorted(set(keys)):
            raise ValueError("claim-authority entries must be sorted and unique")
        return value


class BehavioralContract(FrozenModel):
    intent: NonEmptyStr
    required_behaviors: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    non_goals: tuple[NonEmptyStr, ...] = ()
    verification_requirements: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @field_validator("required_behaviors", "non_goals", "verification_requirements")
    @classmethod
    def text_is_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("behavioral contract values must be sorted and unique")
        return value


class ConfidenceAssessment(FrozenModel):
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rationale: NonEmptyStr
    basis_evidence_refs: NonEmptyEvidenceRefTuple

    @field_validator("basis_evidence_refs")
    @classmethod
    def basis_is_sorted_unique(cls, value: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("confidence basis must be sorted and unique")
        return value


class EvaluationAttestation(FrozenModel):
    case_ref: EvaluationCaseRef
    # Identity/version is exact; omitting a digest avoids a self-hash when the attestation is
    # embedded in the candidate or artifact it evaluates.
    subject_ref: ExactRecordRef
    result: EvaluationResult
    evaluator: ActorRef
    evaluator_version: SemVer
    evaluated_at: UtcDateTime
    result_digest: Sha256Digest
    partition: Partition
    independent_of_proposer: bool


class Approval(FrozenModel):
    decision: ApprovalDecision
    approver: ActorRef
    decided_at: UtcDateTime
    policy_version: SemVer
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def approver_is_human(self) -> "Approval":
        if self.approver.kind not in {ActorKind.USER, ActorKind.HUMAN_REVIEWER}:
            raise ValueError("approval must be attributable to a human")
        return self


class ConflictRecord(FrozenModel):
    artifact_ref: ArtifactRef
    resolution: ConflictResolution
    rationale: NonEmptyStr


class RouteAlternative(FrozenModel):
    route: ArtifactRoute
    eligible: bool
    reason: NonEmptyStr


class ConstructionBoundary(FrozenModel):
    construction_cutoff: UtcDateTime
    split_manifest_digest: Sha256Digest
    custody_policy_version: SemVer
    held_out_sealed: Literal[True] = True


class TargetCapabilityProfile(FrozenModel):
    profile_id: Identifier
    profile_version: SemVer
    target_family: Identifier
    supported_artifact_kinds: Annotated[tuple[ArtifactKind, ...], Field(min_length=1)]
    supported_scope_dimensions: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    supports_precedence: bool
    supports_evidence_trace: bool
    supports_authority_labels: bool
    supports_expiry: bool
    max_context_tokens: int = Field(gt=0)
    maximum_sensitivity: SensitivityClass
    fail_on_material_loss: Literal[True] = True

    @field_validator("supported_artifact_kinds")
    @classmethod
    def kinds_are_sorted_unique(cls, value: tuple[ArtifactKind, ...]) -> tuple[ArtifactKind, ...]:
        raw = tuple(item.value for item in value)
        if not strings_are_sorted_unique(raw):
            raise ValueError("supported artifact kinds must be sorted and unique")
        return value

    @field_validator("supported_scope_dimensions")
    @classmethod
    def dimensions_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("supported scope dimensions must be sorted and unique")
        return value


class RenderingLoss(FrozenModel):
    field_path: NonEmptyStr
    materiality: LossMateriality
    reason: NonEmptyStr
    artifact_ref: ArtifactRef | None = None


class RenderedEntry(FrozenModel):
    entry_id: Identifier
    output_path: NonEmptyStr
    content_digest: Sha256Digest
    byte_length: int = Field(ge=0)
    artifact_ref: ArtifactRef
    evidence_refs: NonEmptyEvidenceRefTuple
    precedence: int
    scope_digest: Sha256Digest
    behavioral_contract_digest: Sha256Digest
    authority_digest: Sha256Digest

    @field_validator("evidence_refs")
    @classmethod
    def evidence_is_sorted_unique(cls, value: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("rendered-entry evidence must be sorted and unique")
        return value


class ScoringRule(FrozenModel):
    scoring_type: ScoringType
    description: NonEmptyStr
    pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)


class EvaluationSetup(FrozenModel):
    instructions: NonEmptyStr
    stimulus: NonEmptyStr
    allowed_context_refs: tuple[AnyRecordRef, ...] = ()
    allowed_tools: IdentifierTuple = ()

    @field_validator("allowed_context_refs")
    @classmethod
    def context_is_sorted_unique(cls, value: tuple[AnyRecordRef, ...]) -> tuple[AnyRecordRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("allowed context must be sorted and unique")
        return value

    @field_validator("allowed_tools")
    @classmethod
    def allowed_tools_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("allowed tools must be sorted and unique")
        return value


class OutcomeAssertion(FrozenModel):
    assertion_id: Identifier
    claim_type: ClaimType
    status: AssertionStatus
    statement: NonEmptyStr
    observed_behavior: NonEmptyStr
    expected_behavior: NonEmptyStr
    evaluation_setup: NonEmptyStr
    evaluation_stimulus: NonEmptyStr
    failure_criteria: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    scoring_rule: ScoringRule
    scope: Scope

    @field_validator("failure_criteria")
    @classmethod
    def criteria_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("failure criteria must be sorted and unique")
        return value
