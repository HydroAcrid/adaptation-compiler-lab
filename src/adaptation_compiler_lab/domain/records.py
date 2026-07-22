"""The eight versioned top-level domain contracts."""

from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from adaptation_compiler_lab.domain.base import (
    ActorRef,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
    UtcDateTime,
    VersionedRecord,
)
from adaptation_compiler_lab.domain.enums import (
    ActorKind,
    ApprovalDecision,
    ArtifactKind,
    ArtifactRoute,
    ArtifactState,
    AssertionStatus,
    AuthorityClass,
    ClaimType,
    ConflictResolution,
    EvaluationCaseKind,
    EvaluationCaseState,
    EvaluationResult,
    EvidenceState,
    LessonCandidateState,
    LessonKind,
    LossMateriality,
    OutcomeKind,
    Partition,
    PermittedUse,
    PrivacyReviewState,
    RecordKind,
    RedactionState,
    ReleaseManifestState,
    SensitivityClass,
    SourceClass,
    TargetPackState,
)
from adaptation_compiler_lab.domain.references import (
    ArtifactRef,
    CaptureReceiptRef,
    ConsentReceiptRef,
    EvaluationCaseRef,
    EvidenceRef,
    LessonCandidateRef,
    OutcomeRef,
    ReleaseRef,
    TaskRecordRef,
)
from adaptation_compiler_lab.domain.values import (
    Approval,
    BehavioralContract,
    ClaimAuthoritySet,
    ConfidenceAssessment,
    ConflictRecord,
    ConstructionBoundary,
    EnvironmentSnapshot,
    EvaluationAttestation,
    EvaluationSetup,
    EvidenceLinks,
    OutcomeAssertion,
    PayloadReference,
    PrivacyContext,
    RenderedEntry,
    RenderingLoss,
    Scope,
    ScoringRule,
    SyntheticOrigin,
    TargetCapabilityProfile,
    Transformation,
    refs_are_sorted_unique,
    strings_are_sorted_unique,
)


def _enum_values_are_sorted_unique(values: tuple[object, ...]) -> bool:
    raw = tuple(str(value) for value in values)
    return strings_are_sorted_unique(raw)


class TaskRecord(VersionedRecord):
    """Provenance envelope for one bounded completed source-agent episode."""

    record_type: Literal[RecordKind.TASK_RECORD] = RecordKind.TASK_RECORD
    subject_id: Identifier
    scope: Scope
    source_agent: ActorRef
    environment: EnvironmentSnapshot
    started_at: UtcDateTime
    completed_at: UtcDateTime
    prompt_evidence_refs: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]
    input_evidence_refs: tuple[EvidenceRef, ...] = ()
    output_evidence_refs: tuple[EvidenceRef, ...] = ()
    outcome_refs: tuple[OutcomeRef, ...] = ()
    privacy: PrivacyContext
    partition: Partition

    @field_validator(
        "prompt_evidence_refs", "input_evidence_refs", "output_evidence_refs", "outcome_refs"
    )
    @classmethod
    def refs_must_be_sorted_unique(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if not refs_are_sorted_unique(value):  # type: ignore[arg-type]
            raise ValueError("record references must be sorted and unique")
        return value

    @model_validator(mode="after")
    def task_is_bounded(self) -> "TaskRecord":
        if self.source_agent.kind is not ActorKind.AGENT:
            raise ValueError("source_agent must identify an agent")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.subject_id not in self.scope.subject_ids:
            raise ValueError("task subject must be included in task scope")
        return self


class Outcome(VersionedRecord):
    """Scoped assessment of a completed task; it never erases other assessments."""

    record_type: Literal[RecordKind.OUTCOME] = RecordKind.OUTCOME
    task_ref: TaskRecordRef
    kind: OutcomeKind
    assessed_at: UtcDateTime
    evaluator: ActorRef
    assertions: tuple[OutcomeAssertion, ...] = ()
    supporting_evidence_refs: tuple[EvidenceRef, ...] = ()
    contradicting_evidence_refs: tuple[EvidenceRef, ...] = ()
    scope: Scope
    environment: EnvironmentSnapshot
    privacy: PrivacyContext
    partition: Partition

    @field_validator("supporting_evidence_refs", "contradicting_evidence_refs")
    @classmethod
    def evidence_must_be_sorted_unique(
        cls, value: tuple[EvidenceRef, ...]
    ) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("outcome evidence must be sorted and unique")
        return value

    @field_validator("assertions")
    @classmethod
    def assertions_must_be_sorted_unique(
        cls, value: tuple[OutcomeAssertion, ...]
    ) -> tuple[OutcomeAssertion, ...]:
        ids = tuple(item.assertion_id for item in value)
        if not strings_are_sorted_unique(ids):
            raise ValueError("outcome assertions must have sorted unique identifiers")
        return value

    @model_validator(mode="after")
    def known_outcomes_have_support(self) -> "Outcome":
        if self.kind is OutcomeKind.UNKNOWN:
            return self
        if not self.assertions:
            raise ValueError("known outcome requires at least one structured assertion")
        if not self.supporting_evidence_refs:
            raise ValueError("known outcome requires supporting evidence")
        evaluation_first_kinds = {
            OutcomeKind.CORRECTION,
            OutcomeKind.FAILURE,
            OutcomeKind.REJECTED,
            OutcomeKind.REVERTED,
        }
        triggering_statuses = {
            AssertionStatus.CORRECTED,
            AssertionStatus.FAILED,
            AssertionStatus.REJECTED,
        }
        if self.kind in evaluation_first_kinds and not any(
            assertion.status in triggering_statuses for assertion in self.assertions
        ):
            raise ValueError(
                "correction, failure, rejection, or revert requires a triggering assertion"
            )
        return self


class EvidenceV1(VersionedRecord):
    """Atomic observation or immutable observation reference in the raw boundary."""

    model_config: ClassVar[ConfigDict] = ConfigDict(title="Evidence")

    record_type: Literal[RecordKind.EVIDENCE] = RecordKind.EVIDENCE
    observed_at: UtcDateTime
    producer: ActorRef
    source_class: SourceClass
    authority_class: AuthorityClass
    authority_reason: NonEmptyStr
    allowed_claim_types: Annotated[tuple[ClaimType, ...], Field(min_length=1)]
    state: EvidenceState
    redaction_state: RedactionState
    payload: PayloadReference | None
    task_ref: TaskRecordRef | None = None
    outcome_ref: OutcomeRef | None = None
    evaluation_case_ref: EvaluationCaseRef | None = None
    synthetic_origin: SyntheticOrigin | None = None
    parent_evidence_refs: tuple[EvidenceRef, ...] = ()
    transformation: Transformation | None = None
    scope: Scope
    privacy: PrivacyContext
    partition: Partition

    @field_validator("allowed_claim_types")
    @classmethod
    def claim_types_are_sorted_unique(cls, value: tuple[ClaimType, ...]) -> tuple[ClaimType, ...]:
        if not _enum_values_are_sorted_unique(value):
            raise ValueError("allowed claim types must be sorted and unique")
        return value

    @field_validator("parent_evidence_refs")
    @classmethod
    def parents_are_sorted_unique(cls, value: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("parent evidence must be sorted and unique")
        return value

    @model_validator(mode="after")
    def provenance_context_is_well_formed(self) -> "EvidenceV1":
        primary_contexts = sum(
            context is not None
            for context in (self.task_ref, self.evaluation_case_ref, self.synthetic_origin)
        )
        if primary_contexts != 1:
            raise ValueError("evidence requires exactly one provenance context")
        if self.outcome_ref is not None and self.task_ref is None:
            raise ValueError("outcome-derived evidence must also reference its task")
        if self.state is EvidenceState.RAW:
            if self.payload is None or self.parent_evidence_refs or self.transformation is not None:
                raise ValueError("raw evidence requires payload and cannot have derivation lineage")
            if self.redaction_state is RedactionState.TOMBSTONED:
                raise ValueError("raw evidence cannot be tombstoned")
        elif self.state is EvidenceState.DERIVED:
            if self.payload is None or not self.parent_evidence_refs or self.transformation is None:
                raise ValueError("derived evidence requires payload, parents, and transformation")
            if set(self.parent_evidence_refs) != set(self.transformation.input_evidence_refs):
                raise ValueError("transformation inputs must equal parent evidence")
        else:
            if self.payload is not None or self.redaction_state is not RedactionState.TOMBSTONED:
                raise ValueError("tombstoned evidence has no payload and is explicitly tombstoned")
        if self.source_class is SourceClass.EXPLICIT_USER_FEEDBACK and (
            self.task_ref is None or self.producer.kind is not ActorKind.USER
        ):
            raise ValueError("explicit user feedback requires a task and user producer")
        if self.source_class is SourceClass.SYNTHETIC:
            if self.synthetic_origin is None or self.partition is not Partition.SYNTHETIC:
                raise ValueError("synthetic evidence requires a synthetic origin and partition")
            if self.authority_class is not AuthorityClass.SYNTHETIC_ONLY:
                raise ValueError("synthetic evidence has synthetic-only authority")
        if self.partition is Partition.HELD_OUT:
            forbidden = {PermittedUse.CONSTRUCTION, PermittedUse.PROMOTION}
            if forbidden & set(self.privacy.permitted_uses):
                raise ValueError("held-out evidence cannot be used for construction or promotion")
        return self


class Evidence(EvidenceV1):
    """Evidence v1.0 compatibility plus exact signed-governance references in v1.1."""

    model_config: ClassVar[ConfigDict] = ConfigDict(title="Evidence")
    # Pydantic supports a schema-discriminating field widening here; other records retain the
    # base Literal["1.0"] contract and the serializer admits 1.1 only for Evidence.
    schema_version: Literal["1.0", "1.1"] = "1.0"  # type: ignore[assignment]
    consent_receipt_ref: ConsentReceiptRef | None = None
    capture_receipt_ref: CaptureReceiptRef | None = None

    @model_validator(mode="after")
    def governance_references_match_schema_and_source(self) -> "Evidence":
        references = (self.consent_receipt_ref, self.capture_receipt_ref)
        if self.schema_version == "1.0":
            if any(reference is not None for reference in references):
                raise ValueError("Evidence v1.0 cannot carry governance references")
            return self
        if self.source_class is SourceClass.SYNTHETIC:
            if any(reference is not None for reference in references):
                raise ValueError("synthetic Evidence v1.1 does not claim real consent or capture")
            return self
        if any(reference is None for reference in references):
            raise ValueError(
                "non-synthetic Evidence v1.1 requires exact consent and capture references"
            )
        return self


class EvaluationCase(VersionedRecord):
    """Reviewable and replayable behavioral check."""

    record_type: Literal[RecordKind.EVALUATION_CASE] = RecordKind.EVALUATION_CASE
    state: EvaluationCaseState
    kind: EvaluationCaseKind
    setup: EvaluationSetup
    expected_behaviors: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    failure_criteria: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    scoring_rule: ScoringRule
    environment: EnvironmentSnapshot
    scope: Scope
    source_task_ref: TaskRecordRef | None = None
    source_outcome_ref: OutcomeRef | None = None
    source_evidence_refs: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]
    partition: Partition
    privacy: PrivacyContext
    review: Approval | None = None

    @field_validator("expected_behaviors", "failure_criteria")
    @classmethod
    def requirements_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("evaluation requirements must be sorted and unique")
        return value

    @field_validator("source_evidence_refs")
    @classmethod
    def evidence_is_sorted_unique(cls, value: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("evaluation evidence must be sorted and unique")
        return value

    @model_validator(mode="after")
    def case_review_and_origin_are_consistent(self) -> "EvaluationCase":
        if self.source_outcome_ref is not None and self.source_task_ref is None:
            raise ValueError("outcome-derived case must identify the source task")
        reviewed = self.state in {EvaluationCaseState.REVIEWED, EvaluationCaseState.APPROVED}
        if self.state is EvaluationCaseState.CANDIDATE and self.review is not None:
            raise ValueError("candidate evaluation case cannot carry a review decision")
        if reviewed and (
            self.review is None or self.review.decision is not ApprovalDecision.APPROVED
        ):
            raise ValueError("reviewed evaluation case requires human approval")
        if self.state is EvaluationCaseState.REJECTED and (
            self.review is None or self.review.decision is not ApprovalDecision.REJECTED
        ):
            raise ValueError("rejected evaluation case requires rejection record")
        if self.review is not None and (
            self.review.policy_version != self.policy_version
            or self.review.decided_at != self.created_at
        ):
            raise ValueError("evaluation review must bind the exact policy and record version")
        if self.partition is Partition.HELD_OUT and self.kind is not EvaluationCaseKind.BENCHMARK:
            raise ValueError("held-out cases must be benchmark cases")
        return self


class LessonCandidate(VersionedRecord):
    """Unapproved, disposable hypothesis about transferable behavior."""

    record_type: Literal[RecordKind.LESSON_CANDIDATE] = RecordKind.LESSON_CANDIDATE
    state: LessonCandidateState
    lesson_kind: LessonKind
    behavioral_contract: BehavioralContract
    claim_authorities: ClaimAuthoritySet
    scope: Scope
    evidence_links: EvidenceLinks
    source_task_refs: Annotated[tuple[TaskRecordRef, ...], Field(min_length=1)]
    source_outcome_refs: Annotated[tuple[OutcomeRef, ...], Field(min_length=1)]
    evaluation_case_refs: Annotated[tuple[EvaluationCaseRef, ...], Field(min_length=1)]
    evaluation_attestations: tuple[EvaluationAttestation, ...] = ()
    confidence: ConfidenceAssessment
    proposed_routes: Annotated[tuple[ArtifactRoute, ...], Field(min_length=1)]
    insufficient_routes: tuple[ArtifactRoute, ...] = ()
    known_conflicts: tuple[ConflictRecord, ...] = ()
    privacy: PrivacyContext
    authoring_method: Identifier
    authoring_method_version: SemVer
    approval: Approval | None = None

    @field_validator("source_task_refs", "source_outcome_refs", "evaluation_case_refs")
    @classmethod
    def source_refs_are_sorted_unique(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if not refs_are_sorted_unique(value):  # type: ignore[arg-type]
            raise ValueError("candidate source references must be sorted and unique")
        return value

    @field_validator("proposed_routes", "insufficient_routes")
    @classmethod
    def route_sets_are_sorted_unique(
        cls, value: tuple[ArtifactRoute, ...]
    ) -> tuple[ArtifactRoute, ...]:
        raw = tuple(item.value for item in value)
        if list(raw) != sorted(set(raw)):
            raise ValueError("candidate routes must be sorted and unique")
        return value

    @model_validator(mode="after")
    def approval_is_separate_from_proposal(self) -> "LessonCandidate":
        supporting = set(self.evidence_links.supporting)
        if any(
            not set(entry.evidence_refs) <= supporting for entry in self.claim_authorities.entries
        ):
            raise ValueError("candidate claim authority must cite direct supporting evidence")
        decided = self.state in {
            LessonCandidateState.APPROVED,
            LessonCandidateState.REJECTED,
            LessonCandidateState.PROMOTED,
        }
        if decided and self.approval is None:
            raise ValueError("decided candidate requires attributable approval")
        if not decided and self.approval is not None:
            raise ValueError("undecided candidate cannot carry an approval")
        if self.approval is not None:
            expected = (
                ApprovalDecision.REJECTED
                if self.state is LessonCandidateState.REJECTED
                else ApprovalDecision.APPROVED
            )
            if decided and self.approval.decision is not expected:
                raise ValueError("candidate state does not match its human decision")
            if (
                self.approval.policy_version != self.policy_version
                or self.approval.decided_at != self.created_at
            ):
                raise ValueError("candidate approval must bind the exact policy and record version")
        if decided and any(
            attestation.partition is Partition.HELD_OUT
            for attestation in self.evaluation_attestations
        ):
            raise ValueError("held-out attestations cannot approve a lesson candidate")
        if (
            self.approval is not None
            and self.approval.approver.actor_id == self.created_by.actor_id
        ):
            raise ValueError("candidate proposer cannot approve its own proposal")
        for attestation in self.evaluation_attestations:
            subject = attestation.subject_ref
            if (
                subject.record_type is not RecordKind.LESSON_CANDIDATE
                or subject.record_id != self.record_id
                or subject.record_version != self.record_version
                or subject.content_digest is not None
            ):
                raise ValueError(
                    "candidate evaluation attestation must target this exact version "
                    "without a recursive self-digest"
                )
            if (
                attestation.independent_of_proposer
                and attestation.evaluator.actor_id == self.created_by.actor_id
            ):
                raise ValueError("candidate proposer cannot be its independent evaluator")
        return self


_ARTIFACT_ROUTE_FOR_KIND: dict[ArtifactKind, ArtifactRoute] = {
    ArtifactKind.MEMORY: ArtifactRoute.MEMORY,
    ArtifactKind.PREFERENCE: ArtifactRoute.PREFERENCE,
    ArtifactKind.EXAMPLE: ArtifactRoute.EXAMPLE,
    ArtifactKind.PROCEDURE: ArtifactRoute.PROCEDURE,
    ArtifactKind.PROMPT_RULE: ArtifactRoute.PROMPT_RULE,
    ArtifactKind.SKILL: ArtifactRoute.SKILL,
    ArtifactKind.TOOL_RECOMMENDATION: ArtifactRoute.TOOL_RECOMMENDATION,
}


class Artifact(VersionedRecord):
    """Typed, target-neutral, independently versioned external adaptation."""

    record_type: Literal[RecordKind.ARTIFACT] = RecordKind.ARTIFACT
    artifact_kind: ArtifactKind
    state: ArtifactState
    behavioral_contract: BehavioralContract
    claim_authorities: ClaimAuthoritySet
    scope: Scope
    source_candidate_refs: Annotated[tuple[LessonCandidateRef, ...], Field(min_length=1)]
    evidence_links: EvidenceLinks
    evaluation_attestations: tuple[EvaluationAttestation, ...] = ()
    selected_route: ArtifactRoute
    routing_rationale: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    lower_impact_alternatives: tuple[ArtifactRoute, ...] = ()
    privacy: PrivacyContext
    conflicts: tuple[ConflictRecord, ...] = ()
    priority: int = 0
    review_at: UtcDateTime | None = None
    expires_at: UtcDateTime | None = None
    target_compatibility: tuple[Identifier, ...] = ()
    approval: Approval | None = None
    execution_mode: Literal["advisory_only"] = "advisory_only"
    modifies_model_weights: Literal[False] = False

    @field_validator("source_candidate_refs")
    @classmethod
    def candidates_are_sorted_unique(
        cls, value: tuple[LessonCandidateRef, ...]
    ) -> tuple[LessonCandidateRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("artifact candidate references must be sorted and unique")
        return value

    @field_validator("routing_rationale", "target_compatibility")
    @classmethod
    def text_values_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("artifact values must be sorted and unique")
        return value

    @field_validator("lower_impact_alternatives")
    @classmethod
    def alternatives_are_unique(cls, value: tuple[ArtifactRoute, ...]) -> tuple[ArtifactRoute, ...]:
        raw = tuple(item.value for item in value)
        if list(raw) != sorted(set(raw)):
            raise ValueError("lower-impact alternatives must be sorted and unique")
        return value

    @model_validator(mode="after")
    def enforce_promotion_gates(self) -> "Artifact":
        supporting = set(self.evidence_links.supporting)
        if any(
            not set(entry.evidence_refs) <= supporting for entry in self.claim_authorities.entries
        ):
            raise ValueError("artifact claim authority must cite direct supporting evidence")
        if self.selected_route is not _ARTIFACT_ROUTE_FOR_KIND[self.artifact_kind]:
            raise ValueError("selected route must match durable artifact kind")
        if self.selected_route in {
            ArtifactRoute.EVALUATION_ONLY,
            ArtifactRoute.INACTIVE_TOOL_CANDIDATE,
            ArtifactRoute.INACTIVE_ADAPTER_DATASET_CANDIDATE,
        }:
            raise ValueError("proposal-only route can never become a durable artifact")
        if any(conflict.resolution is ConflictResolution.UNRESOLVED for conflict in self.conflicts):
            raise ValueError("artifact cannot retain unresolved conflicts")
        gated = self.state in {ArtifactState.EVALUATED, ArtifactState.APPROVED}
        if gated and not self.evaluation_attestations:
            raise ValueError("evaluated artifact requires evaluation attestations")
        if (
            self.state in {ArtifactState.DRAFT, ArtifactState.EVALUATED}
            and self.approval is not None
        ):
            raise ValueError("draft or evaluated artifact cannot carry an approval")
        if self.state is ArtifactState.REJECTED and (
            self.approval is None or self.approval.decision is not ApprovalDecision.REJECTED
        ):
            raise ValueError("rejected artifact requires a human rejection record")
        if self.approval is not None and (
            self.approval.policy_version != self.policy_version
            or self.approval.decided_at != self.created_at
        ):
            raise ValueError("artifact approval must bind the exact policy and record version")
        if self.state is ArtifactState.APPROVED:
            if self.approval is None or self.approval.decision is not ApprovalDecision.APPROVED:
                raise ValueError("approved artifact requires human approval")
            if self.approval.approver.actor_id == self.created_by.actor_id:
                raise ValueError("artifact proposer cannot approve its own artifact")
            if self.privacy.review_state is not PrivacyReviewState.APPROVED:
                raise ValueError("approved artifact requires approved privacy review")
            if self.privacy.sensitivity is SensitivityClass.PROHIBITED_SECRET:
                raise ValueError("secret-bearing content cannot become a durable artifact")
            if PermittedUse.PROMOTION not in self.privacy.permitted_uses:
                raise ValueError("approved artifact must be permitted for promotion")
            if any(
                result.partition is Partition.HELD_OUT for result in self.evaluation_attestations
            ):
                raise ValueError("held-out attestations cannot promote an artifact")
            if not any(
                result.result is EvaluationResult.PASSED
                and result.partition is not Partition.HELD_OUT
                and result.independent_of_proposer
                for result in self.evaluation_attestations
            ):
                raise ValueError("approved artifact requires an independent construction-side pass")
        for attestation in self.evaluation_attestations:
            subject = attestation.subject_ref
            if (
                subject.record_type is not RecordKind.ARTIFACT
                or subject.record_id != self.record_id
                or subject.record_version != self.record_version
                or subject.content_digest is not None
            ):
                raise ValueError(
                    "artifact evaluation attestation must target this exact version "
                    "without a recursive self-digest"
                )
            if (
                attestation.independent_of_proposer
                and attestation.evaluator.actor_id == self.created_by.actor_id
            ):
                raise ValueError("artifact proposer cannot be its independent evaluator")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("artifact expiry must follow creation")
        return self


class Release(VersionedRecord):
    """Immutable manifest of exact approved artifact versions."""

    record_type: Literal[RecordKind.RELEASE] = RecordKind.RELEASE
    manifest_state: Literal[ReleaseManifestState.RELEASED] = ReleaseManifestState.RELEASED
    release_version: SemVer
    released_at: UtcDateTime
    artifact_refs: tuple[ArtifactRef, ...]
    is_empty_release: bool
    schema_versions: Annotated[tuple[SemVer, ...], Field(min_length=1)]
    policy_versions: Annotated[tuple[SemVer, ...], Field(min_length=1)]
    construction_boundary: ConstructionBoundary
    development_evaluations: tuple[EvaluationAttestation, ...]
    approval: Approval
    predecessor_ref: ReleaseRef | None = None
    supersedes_refs: tuple[ReleaseRef, ...] = ()
    rollback_target_ref: ReleaseRef | None = None
    target_compatibility: tuple[Identifier, ...] = ()

    @field_validator("artifact_refs", "supersedes_refs")
    @classmethod
    def membership_is_sorted_unique(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if not refs_are_sorted_unique(value):  # type: ignore[arg-type]
            raise ValueError("release references must be sorted and unique")
        return value

    @field_validator("schema_versions", "policy_versions", "target_compatibility")
    @classmethod
    def versions_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("release values must be sorted and unique")
        return value

    @model_validator(mode="after")
    def manifest_is_frozen_and_approved(self) -> "Release":
        if self.is_empty_release != (not self.artifact_refs):
            raise ValueError("empty-release marker must match artifact membership")
        if self.approval.decision is not ApprovalDecision.APPROVED:
            raise ValueError("release requires explicit human approval")
        if self.approval.policy_version != self.policy_version:
            raise ValueError("release approval must use the release policy version")
        if self.approval.decided_at > self.released_at:
            raise ValueError("release approval cannot postdate release freeze")
        if self.artifact_refs and not self.development_evaluations:
            raise ValueError("non-empty release requires development evaluation attestations")
        if any(result.partition is Partition.HELD_OUT for result in self.development_evaluations):
            raise ValueError("held-out results cannot enter a release manifest")
        for reference in (self.predecessor_ref, self.rollback_target_ref):
            if reference is not None and reference.record_id == self.record_id:
                raise ValueError(
                    "release cannot reference itself as predecessor or rollback target"
                )
        return self


class TargetPack(VersionedRecord):
    """Immutable target-specific manifest derived from exactly one frozen release."""

    record_type: Literal[RecordKind.TARGET_PACK] = RecordKind.TARGET_PACK
    state: TargetPackState
    release_ref: ReleaseRef
    target_profile: TargetCapabilityProfile
    renderer_version: SemVer
    entries: tuple[RenderedEntry, ...]
    ordering_rationale: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    omitted_artifact_refs: tuple[ArtifactRef, ...] = ()
    losses: tuple[RenderingLoss, ...] = ()
    warnings: tuple[NonEmptyStr, ...] = ()
    context_token_cost: int = Field(ge=0)
    runtime_selector_digest: Sha256Digest | None = None
    privacy: PrivacyContext
    material_semantics_preserved: bool
    contains_raw_evidence: Literal[False] = False
    modifies_model_weights: Literal[False] = False
    executes_tools: Literal[False] = False

    @field_validator("entries")
    @classmethod
    def entries_are_sorted_unique(
        cls, value: tuple[RenderedEntry, ...]
    ) -> tuple[RenderedEntry, ...]:
        ids = tuple(entry.entry_id for entry in value)
        if not strings_are_sorted_unique(ids):
            raise ValueError("target-pack entries must have sorted unique identifiers")
        return value

    @field_validator("omitted_artifact_refs")
    @classmethod
    def omissions_are_sorted_unique(cls, value: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("omitted artifacts must be sorted and unique")
        return value

    @field_validator("ordering_rationale", "warnings")
    @classmethod
    def text_is_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("target-pack text values must be sorted and unique")
        return value

    @model_validator(mode="after")
    def validated_pack_fails_closed(self) -> "TargetPack":
        material_losses = [
            loss for loss in self.losses if loss.materiality is LossMateriality.MATERIAL
        ]
        if self.state is TargetPackState.VALIDATED:
            if not self.material_semantics_preserved or material_losses:
                raise ValueError("validated pack cannot contain material semantic loss")
            explained_omissions = {
                loss.artifact_ref
                for loss in self.losses
                if loss.artifact_ref is not None
                and loss.materiality is LossMateriality.NON_MATERIAL
            }
            if not set(self.omitted_artifact_refs) <= explained_omissions:
                raise ValueError("validated pack must explain every omission as non-material")
            if self.privacy.review_state is not PrivacyReviewState.APPROVED:
                raise ValueError("validated pack requires approved privacy review")
            if self.privacy.sensitivity is SensitivityClass.PROHIBITED_SECRET:
                raise ValueError("target pack cannot contain secret-bearing content")
            if PermittedUse.TARGET_DELIVERY not in self.privacy.permitted_uses:
                raise ValueError("validated pack must be permitted for target delivery")
            if not self.target_profile.supports_evidence_trace:
                raise ValueError("validated pack target must preserve evidence trace")
            if not self.target_profile.supports_authority_labels:
                raise ValueError("validated pack target must preserve claim-specific authority")
            if self.context_token_cost > self.target_profile.max_context_tokens:
                raise ValueError("validated pack exceeds target context budget")
        return self
