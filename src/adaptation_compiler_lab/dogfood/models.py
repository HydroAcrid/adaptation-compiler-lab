"""Typed values for deterministic longitudinal dogfood transitions."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    Approval,
    ApprovalDecision,
    CaptureReceiptRef,
    ConsentReceiptRef,
    EvaluationCaseRef,
    Evidence,
    EvidenceRef,
    FrozenModel,
    Identifier,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.governance import CaptureReceipt, ConsentReceipt, SignerIdentity
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection, RenderedPack


class DogfoodTransitionKind(StrEnum):
    """The three transition kinds required by Milestone 6A."""

    ADDITION = "addition"
    SCOPED_CORRECTION = "scoped_correction"
    SUPERSESSION = "supersession"
    REVOCATION = "revocation"


class DogfoodFeedbackOutcome(StrEnum):
    """Minimal user feedback after one activated adaptation encounter."""

    HELPED = "helped"
    HURT = "hurt"
    IRRELEVANT = "irrelevant"


class DogfoodContext(FrozenModel):
    """Machine-comparable context used to test activation and leakage."""

    subject_id: Identifier
    target_family: Identifier
    workspace_id: Identifier | None = None
    project_id: Identifier | None = None
    repository_id: Identifier | None = None
    task_class: Identifier | None = None
    environment_id: Identifier | None = None
    condition_labels: tuple[str, ...] = ()
    evaluated_at: UtcDateTime

    @field_validator("condition_labels")
    @classmethod
    def labels_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("dogfood context labels must be sorted and unique")
        return value


class DogfoodTransition(FrozenModel):
    """One approved evidence transition entering the longitudinal compiler."""

    transition_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    kind: DogfoodTransitionKind
    source_evidence: Evidence
    consent: ConsentReceipt
    capture: CaptureReceipt
    signer_identity: SignerIdentity
    evaluation_case_ref: EvaluationCaseRef
    review: Approval
    instruction: ArtifactRenderProjection | None = None
    affected_artifact_id: Identifier | None = None
    supersedes_artifact_ids: tuple[Identifier, ...] = ()
    workflow_started_at: UtcDateTime
    released_at: UtcDateTime
    activated_at: UtcDateTime
    maintenance_actions: int = Field(ge=1)

    @field_validator("supersedes_artifact_ids")
    @classmethod
    def supersessions_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("superseded artifact IDs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def transition_shape_is_exact(self) -> Self:
        if self.review.decision is not ApprovalDecision.APPROVED:
            raise ValueError("dogfood transition requires explicit approval")
        if not (
            self.workflow_started_at
            <= self.review.decided_at
            <= self.released_at
            <= self.activated_at
        ):
            raise ValueError("dogfood workflow timestamps must be monotonic")
        if self.kind is DogfoodTransitionKind.ADDITION:
            if (
                self.instruction is None
                or self.affected_artifact_id is not None
                or self.supersedes_artifact_ids
            ):
                raise ValueError("addition must introduce exactly one instruction")
        elif self.kind is DogfoodTransitionKind.SCOPED_CORRECTION:
            if (
                self.instruction is None
                or self.affected_artifact_id is None
                or self.supersedes_artifact_ids != (self.affected_artifact_id,)
            ):
                raise ValueError("scoped correction must identify exactly one superseded artifact")
        elif self.kind is DogfoodTransitionKind.SUPERSESSION:
            if (
                self.instruction is None
                or self.affected_artifact_id is None
                or self.supersedes_artifact_ids != (self.affected_artifact_id,)
            ):
                raise ValueError("supersession must replace exactly one earlier artifact")
        elif (
            self.instruction is not None
            or self.affected_artifact_id is None
            or self.supersedes_artifact_ids
        ):
            raise ValueError("revocation must remove exactly one earlier artifact")
        return self


class DogfoodInstructionLineage(FrozenModel):
    """Exact consent, capture, evidence, evaluation, and review lineage."""

    artifact_id: Identifier
    artifact_digest: Sha256Digest
    evidence_ref: EvidenceRef
    consent_ref: ConsentReceiptRef
    capture_ref: CaptureReceiptRef
    evaluation_case_ref: EvaluationCaseRef
    review_approver_id: Identifier
    review_policy_version: str


class ScopedSupersession(FrozenModel):
    """A narrower instruction replaces a broader one only where it applies."""

    replacing_artifact_id: Identifier
    replaced_artifact_id: Identifier


class DogfoodPackMeasurement(FrozenModel):
    """Comparable pack size, latency, and maintenance measurements."""

    stage: Annotated[int, Field(ge=1, le=3)]
    pack_digest: Sha256Digest
    target_visible_bytes: int = Field(ge=0)
    primary_instruction_bytes: int = Field(ge=0)
    estimated_target_tokens: int = Field(ge=0)
    byte_growth_from_previous: int
    active_instruction_count: int = Field(ge=0)
    provenance_link_count: int = Field(ge=0)
    update_latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    maintenance_seconds: float = Field(ge=0, allow_inf_nan=False)
    maintenance_actions: int = Field(ge=1)


class DogfoodStageSnapshot(FrozenModel):
    """One immutable compiled release/pack state after a transition."""

    stage: Annotated[int, Field(ge=1, le=3)]
    transition_id: Identifier
    transition_kind: DogfoodTransitionKind
    release_id: Identifier
    release_digest: Sha256Digest
    rendered_pack: RenderedPack
    active_instructions: tuple[ArtifactRenderProjection, ...]
    lineages: tuple[DogfoodInstructionLineage, ...]
    scoped_supersessions: tuple[ScopedSupersession, ...] = ()
    revoked_artifact_ids: tuple[Identifier, ...] = ()
    measurement: DogfoodPackMeasurement

    @model_validator(mode="after")
    def snapshot_is_coherent(self) -> Self:
        artifact_ids = tuple(item.artifact_ref.record_id for item in self.active_instructions)
        lineage_ids = tuple(item.artifact_id for item in self.lineages)
        if artifact_ids != tuple(sorted(set(artifact_ids))):
            raise ValueError("active instructions must be sorted and unique")
        if lineage_ids != artifact_ids:
            raise ValueError("every active instruction must have exact lineage")
        if self.rendered_pack.pack_digest != self.measurement.pack_digest:
            raise ValueError("stage measurement must bind the exact rendered pack")
        if self.measurement.active_instruction_count != len(artifact_ids):
            raise ValueError("active instruction measurement is inconsistent")
        return self


class LongitudinalDogfoodResult(FrozenModel):
    """Exactly three deterministic stage snapshots."""

    result_version: Literal["1.0.0"] = "1.0.0"
    stages: Annotated[tuple[DogfoodStageSnapshot, ...], Field(min_length=3, max_length=3)]
    sealed_external_validation_accessed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0

    @model_validator(mode="after")
    def stages_are_exact(self) -> Self:
        if tuple(item.stage for item in self.stages) != (1, 2, 3):
            raise ValueError("dogfood result must contain stages 1, 2, and 3 in order")
        return self


class DogfoodDeliveryReceipt(FrozenModel):
    """Receipt for materializing one pack into a clean future Codex workspace."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    stage: Annotated[int, Field(ge=1, le=3)]
    pack_digest: Sha256Digest
    written_relative_paths: tuple[str, ...]
    workspace_manifest_digest: Sha256Digest
    destination_was_empty: Literal[True] = True
    fresh_codex_session_required: Literal[True] = True
    codex_session_started: Literal[False] = False
    provider_billed_calls: Literal[0] = 0

    @field_validator("written_relative_paths")
    @classmethod
    def paths_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("delivery paths must be sorted and unique")
        return value


class ActivationFeedback(FrozenModel):
    """Append-only lightweight feedback for one activated pack encounter."""

    feedback_version: Literal["1.0.0"] = "1.0.0"
    feedback_id: Identifier
    subject_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    task_id: Identifier
    pack_digest: Sha256Digest
    outcome: DogfoodFeedbackOutcome
    relevant_instruction_ids: tuple[Identifier, ...]
    activated_instruction_ids: tuple[Identifier, ...]
    correction_key: Identifier | None = None
    correction_required: bool = False
    recorded_at: UtcDateTime
    recorded_by: Identifier

    @field_validator("relevant_instruction_ids", "activated_instruction_ids")
    @classmethod
    def instruction_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("feedback instruction IDs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def correction_is_attributable(self) -> Self:
        if self.correction_required != (self.correction_key is not None):
            raise ValueError("correction-required feedback needs exactly one correction key")
        return self


class DogfoodMetrics(FrozenModel):
    """Aggregate longitudinal activation and maintenance metrics."""

    feedback_count: int = Field(ge=0)
    helped_count: int = Field(ge=0)
    hurt_count: int = Field(ge=0)
    irrelevant_count: int = Field(ge=0)
    repeated_correction_count: int = Field(ge=0)
    correct_activation_count: int = Field(ge=0)
    false_activation_count: int = Field(ge=0)
    missed_activation_count: int = Field(ge=0)
    stage_pack_bytes: tuple[int, int, int]
    stage_update_latency_seconds: tuple[float, float, float]
    total_maintenance_seconds: float = Field(ge=0, allow_inf_nan=False)
    total_maintenance_actions: int = Field(ge=0)
