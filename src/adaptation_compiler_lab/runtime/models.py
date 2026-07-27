"""Typed portable/runtime representation boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    ArtifactRef,
    CaptureReceiptRef,
    ConsentReceiptRef,
    EvaluationCaseRef,
    EvidenceLinks,
    EvidenceRef,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    ReleaseRef,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import Scope
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    ScopeDimension,
)


class RuntimeClauseRole(StrEnum):
    """Semantic role retained externally for each target-visible clause."""

    ACTIONABLE_BEHAVIOR = "actionable_behavior"
    NECESSARY_SCOPE = "necessary_scope"
    NECESSARY_PRECEDENCE = "necessary_precedence"
    NECESSARY_VERIFICATION = "necessary_verification"


class GovernedLifecycleEvent(FrozenModel):
    """Content-addressed lifecycle history retained outside the target prompt."""

    event_id: Identifier
    stage: int = Field(ge=1)
    transition_kind: Literal[
        "addition",
        "scoped_correction",
        "supersession",
        "revocation",
    ]
    evidence_ref: EvidenceRef
    consent_ref: ConsentReceiptRef
    capture_ref: CaptureReceiptRef
    evaluation_case_ref: EvaluationCaseRef
    review_digest: Sha256Digest
    review_approver_id: Identifier
    review_policy_version: NonEmptyStr
    introduced_artifact_ref: ArtifactRef | None = None
    affected_artifact_id: Identifier | None = None
    supersedes_artifact_ids: tuple[Identifier, ...] = ()
    released_at: UtcDateTime
    activated_at: UtcDateTime

    @field_validator("supersedes_artifact_ids")
    @classmethod
    def supersessions_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("governed lifecycle supersessions must be sorted and unique")
        return value


class ArtifactGovernanceBinding(FrozenModel):
    """Complete active artifact lineage retained in the external release."""

    artifact_ref: ArtifactRef
    scope: Scope
    evidence_links: EvidenceLinks
    evaluation_case_refs: tuple[EvaluationCaseRef, ...] = Field(min_length=1)
    consent_refs: tuple[ConsentReceiptRef, ...] = Field(min_length=1)
    capture_refs: tuple[CaptureReceiptRef, ...] = Field(min_length=1)
    review_approver_ids: tuple[Identifier, ...] = Field(min_length=1)
    review_policy_versions: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def binding_is_sorted_and_exact(self) -> Self:
        for name in (
            "evaluation_case_refs",
            "consent_refs",
            "capture_refs",
            "review_approver_ids",
            "review_policy_versions",
        ):
            values = getattr(self, name)
            keys = tuple(str(item) for item in values)
            if keys != tuple(sorted(set(keys))):
                raise ValueError(f"{name} must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ExternalGovernedRelease(FrozenModel):
    """Portable user-owned release; complete for audit and rollback, not target-visible."""

    external_release_version: Literal["1.0.0"] = "1.0.0"
    release_ref: ReleaseRef
    renderer_id: Literal["compact-runtime-projection"] = "compact-runtime-projection"
    renderer_version: Literal["1.0.0"] = "1.0.0"
    parent_release_digest: Sha256Digest | None = None
    source_snapshot_digest: Sha256Digest
    active_artifacts: tuple[ArtifactRenderProjection, ...]
    active_bindings: tuple[ArtifactGovernanceBinding, ...]
    lifecycle_history: tuple[GovernedLifecycleEvent, ...] = Field(min_length=1)
    scoped_supersessions: tuple[tuple[Identifier, Identifier], ...] = ()
    revoked_artifact_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def release_is_coherent(self) -> Self:
        artifact_ids = tuple(item.artifact_ref.record_id for item in self.active_artifacts)
        binding_ids = tuple(item.artifact_ref.record_id for item in self.active_bindings)
        if artifact_ids != tuple(sorted(set(artifact_ids))):
            raise ValueError("external release artifacts must be sorted and unique")
        if binding_ids != artifact_ids:
            raise ValueError("every external release artifact requires exact governance binding")
        for artifact, binding in zip(
            self.active_artifacts,
            self.active_bindings,
            strict=True,
        ):
            if binding.artifact_ref != artifact.artifact_ref:
                raise ValueError("governance binding must reference the exact artifact version")
            if binding.scope != artifact.scope:
                raise ValueError("governance binding scope must exactly match its artifact")
            if binding.evidence_links != artifact.evidence_links:
                raise ValueError(
                    "governance binding evidence links must exactly match its artifact"
                )
        if self.revoked_artifact_ids != tuple(sorted(set(self.revoked_artifact_ids))):
            raise ValueError("revoked artifact IDs must be sorted and unique")
        if any(item.revoked for item in self.active_artifacts):
            raise ValueError("revoked artifacts cannot be active in an external release")
        if set(artifact_ids) & set(self.revoked_artifact_ids):
            raise ValueError("revoked artifact IDs cannot also be active")
        if self.scoped_supersessions != tuple(sorted(set(self.scoped_supersessions))):
            raise ValueError("scoped supersessions must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeProjectionContext(FrozenModel):
    """Known and unknown scope dimensions at projection time."""

    known_dimensions: tuple[ScopeDimension, ...]
    target_profile_id: Identifier | None = None
    subject_id: Identifier | None = None
    workspace_id: Identifier | None = None
    project_id: Identifier | None = None
    repository_id: Identifier | None = None
    task_class: Identifier | None = None
    target_family: Identifier | None = None
    environment_id: Identifier | None = None
    condition_labels: tuple[NonEmptyStr, ...] = ()
    evaluated_at: UtcDateTime | None = None

    @field_validator("known_dimensions")
    @classmethod
    def dimensions_are_sorted_unique(
        cls, value: tuple[ScopeDimension, ...]
    ) -> tuple[ScopeDimension, ...]:
        raw = tuple(item.value for item in value)
        if raw != tuple(sorted(set(raw))):
            raise ValueError("known scope dimensions must be sorted and unique")
        return value

    @field_validator("condition_labels")
    @classmethod
    def labels_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("runtime context labels must be sorted and unique")
        return value


class RuntimeClause(FrozenModel):
    """One target-independent effective runtime clause."""

    text: NonEmptyStr
    roles: Annotated[tuple[RuntimeClauseRole, ...], Field(min_length=1)]
    source_artifact_refs: Annotated[tuple[ArtifactRef, ...], Field(min_length=1)]

    @field_validator("roles")
    @classmethod
    def roles_are_sorted_unique(
        cls, value: tuple[RuntimeClauseRole, ...]
    ) -> tuple[RuntimeClauseRole, ...]:
        raw = tuple(item.value for item in value)
        if raw != tuple(sorted(set(raw))):
            raise ValueError("runtime clause roles must be sorted and unique")
        return value

    @field_validator("source_artifact_refs")
    @classmethod
    def sources_are_sorted_unique(cls, value: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
        keys = tuple((item.record_id, item.record_version, item.content_digest) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("runtime clause sources must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CanonicalRuntimeProjection(FrozenModel):
    """Target-independent active clauses derived from one governed release."""

    projection_version: Literal["1.0.0"] = "1.0.0"
    external_release_digest: Sha256Digest
    release_ref: ReleaseRef
    context: RuntimeProjectionContext
    clauses: tuple[RuntimeClause, ...]
    omitted_artifact_refs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def clauses_and_omissions_are_unique(self) -> Self:
        clause_digests = tuple(item.content_digest for item in self.clauses)
        if clause_digests != tuple(dict.fromkeys(clause_digests)):
            raise ValueError("runtime projection contains duplicate clauses")
        omitted = tuple(item.record_id for item in self.omitted_artifact_refs)
        if omitted != tuple(sorted(set(omitted))):
            raise ValueError("runtime omissions must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClauseProvenanceBinding(FrozenModel):
    """Hidden exact binding from one rendered clause to governed lineage."""

    clause_digest: Sha256Digest
    rendered_fragment_digest: Sha256Digest
    source_binding_digests: tuple[Sha256Digest, ...] = Field(min_length=1)

    @field_validator("source_binding_digests")
    @classmethod
    def binding_digests_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("source binding digests must be sorted and unique")
        return value


class RuntimeProjectionManifest(FrozenModel):
    """External manifest; never delivered with the target-visible projection."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    external_release_digest: Sha256Digest
    runtime_projection_digest: Sha256Digest
    target_renderer_id: Identifier
    target_renderer_version: NonEmptyStr
    rendered_content_digest: Sha256Digest
    rendered_utf8_bytes: int = Field(ge=0)
    clause_bindings: tuple[ClauseProvenanceBinding, ...]

    @model_validator(mode="after")
    def clauses_are_unique(self) -> Self:
        digests = tuple(item.clause_digest for item in self.clause_bindings)
        if digests != tuple(dict.fromkeys(digests)):
            raise ValueError("runtime manifest contains duplicate clause bindings")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
