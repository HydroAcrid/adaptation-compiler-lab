"""Target-rendering boundary models.

These models are deliberately projections rather than new domain records.  A release service
resolves exact domain references and supplies the minimum reviewed data a renderer needs.  Raw
evidence has no field in this boundary.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import (
    ArtifactKind,
    Partition,
)
from adaptation_compiler_lab.domain.references import ArtifactRef, EvaluationCaseRef, ReleaseRef
from adaptation_compiler_lab.domain.values import (
    BehavioralContract,
    ClaimAuthoritySet,
    EvidenceLinks,
    PrivacyContext,
    Scope,
    TargetCapabilityProfile,
)


class TargetKind(StrEnum):
    """File-only targets implemented by the prototype."""

    GENERIC_JSON = "generic-json"
    GENERIC_MARKDOWN = "generic-markdown"
    CODEX = "codex"
    CLAUDE_CODE = "claude-code"


class ScopeDimension(StrEnum):
    """Scope dimensions a renderer must preserve when present."""

    SUBJECT_IDS = "subject_ids"
    WORKSPACE_IDS = "workspace_ids"
    PROJECT_IDS = "project_ids"
    REPOSITORY_IDS = "repository_ids"
    TASK_CLASSES = "task_classes"
    TARGET_FAMILIES = "target_families"
    ENVIRONMENT_IDS = "environment_ids"
    ACTIVATION_CONDITIONS = "activation_conditions"
    EXCLUSIONS = "exclusions"
    VALIDITY_WINDOW = "validity_window"


class TargetSurface(StrEnum):
    """Allowlisted output surfaces; renderers never invent a new one."""

    JSON = "json"
    MARKDOWN = "markdown"
    AGENTS_MD = "agents_md"
    AGENT_SKILL = "agent_skill"
    CLAUDE_MD = "claude_md"
    CLAUDE_RULE = "claude_rule"
    CLAUDE_SKILL = "claude_skill"


class ArtifactRenderProjection(FrozenModel):
    """Minimum approved behavioral artifact accepted by file renderers."""

    artifact_ref: ArtifactRef
    artifact_type: ArtifactKind
    behavioral_contract: BehavioralContract
    scope: Scope
    evidence_links: EvidenceLinks
    evaluation_cases: tuple[EvaluationCaseRef, ...] = Field(min_length=1)
    claim_authorities: ClaimAuthoritySet
    privacy: PrivacyContext
    precedence: int = Field(default=0, ge=-10_000, le=10_000)
    review_at: UtcDateTime | None = None
    expires_at: UtcDateTime | None = None
    target_compatibility: tuple[Identifier, ...] = ()
    required: bool = True
    revoked: bool = False
    source_partitions: tuple[Partition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def construction_only(self) -> Self:
        if Partition.HELD_OUT in self.source_partitions:
            raise ValueError("held-out material cannot influence a rendered artifact")
        supporting = set(self.evidence_links.supporting)
        if any(
            not set(item.evidence_refs) <= supporting for item in self.claim_authorities.entries
        ):
            raise ValueError("claim authority must cite direct supporting evidence")
        return self


class ReleaseRenderProjection(FrozenModel):
    """Resolved immutable release view supplied to a renderer."""

    release_ref: ReleaseRef
    release_version: SemVer
    policy_version: SemVer
    artifacts: tuple[ArtifactRenderProjection, ...]
    target_compatibility: tuple[Identifier, ...] = ()
    explicit_empty: bool = False

    @model_validator(mode="after")
    def coherent_membership(self) -> Self:
        if self.explicit_empty != (len(self.artifacts) == 0):
            raise ValueError("explicit_empty must exactly match empty artifact membership")
        keys = [
            (item.artifact_ref.record_id, item.artifact_ref.record_version)
            for item in self.artifacts
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("release contains a duplicate exact artifact version")
        return self


class FileTargetCapabilityProfile(FrozenModel):
    """Canonical target capabilities plus file-surface and byte limits."""

    capabilities: TargetCapabilityProfile
    target: TargetKind
    documentation_uri: NonEmptyStr
    documentation_checked_on: NonEmptyStr
    supported_surfaces: frozenset[TargetSurface]
    max_entries: int = Field(gt=0)
    max_total_bytes: int = Field(gt=0)
    max_primary_instruction_bytes: int = Field(gt=0)
    max_primary_instruction_lines: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def target_matches_canonical_profile(self) -> Self:
        if self.capabilities.target_family != self.target.value:
            raise ValueError("file target must match canonical target-family capability")
        return self


class RenderedFile(FrozenModel):
    """One deterministic UTF-8 file with a safe relative POSIX path."""

    path: NonEmptyStr
    content: str
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def safe_relative_path(self) -> Self:
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
            raise ValueError("rendered file path must be relative and traversal-free")
        if "\\" in self.path:
            raise ValueError("rendered file path must use POSIX separators")
        return self


class RenderedEntry(FrozenModel):
    """Trace from a rendered file entry to canonical artifact and evidence records."""

    artifact_id: Identifier
    artifact_version: SemVer
    artifact_digest: Sha256Digest
    paths: tuple[NonEmptyStr, ...] = Field(min_length=1)
    supporting_evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    contradicting_evidence_ids: tuple[Identifier, ...] = ()
    scope_limiting_evidence_ids: tuple[Identifier, ...] = ()
    authority_digest: Sha256Digest


class RenderOmission(FrozenModel):
    """An intentional, non-material omission such as an out-of-target artifact."""

    artifact_id: Identifier
    reason: NonEmptyStr


class RenderedPack(FrozenModel):
    """Deterministic output of one renderer invocation."""

    renderer_id: Identifier
    renderer_version: SemVer
    target_profile_id: Identifier
    target_profile_version: SemVer
    release_id: Identifier
    release_version: SemVer
    release_digest: Sha256Digest
    files: tuple[RenderedFile, ...]
    entries: tuple[RenderedEntry, ...]
    omissions: tuple[RenderOmission, ...] = ()
    warnings: tuple[NonEmptyStr, ...] = ()
    pack_digest: Sha256Digest
    total_bytes: int = Field(ge=0)
