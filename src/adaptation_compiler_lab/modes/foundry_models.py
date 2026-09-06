"""Typed provenance, review, and catalog records for curated capability Modes."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.governance import SignatureEnvelope
from adaptation_compiler_lab.modes.models import CapabilityMode
from adaptation_compiler_lab.serialization import canonical_digest


class CapabilityResourceKind(StrEnum):
    """Declarative resource classes admitted by the first Foundry policy."""

    INSTRUCTION = "instruction"
    REFERENCE = "reference"
    EXAMPLE = "example"
    STATIC_ASSET = "static_asset"
    SCRIPT = "script"
    HOOK = "hook"
    DEPENDENCY = "dependency"
    TOOL = "tool"


class SourceReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    REJECTED = "rejected"
    REVIEWED = "reviewed"


class CatalogEvaluationStatus(StrEnum):
    CURATED_UNPROVEN = "curated_unproven"
    FAILED = "failed"
    PRODUCT_EVALUATED = "product_evaluated"
    REVOKED = "revoked"


class SourceCapabilityRequirementV1(FrozenModel):
    """One upstream assumption; recording it never grants the capability."""

    requirement_version: Literal["1.0.0"] = "1.0.0"
    requirement_id: Identifier
    kind: Literal[
        "agent_feature",
        "external_account",
        "filesystem_write",
        "model",
        "network",
        "provider_tool",
        "subagent",
        "system_tool",
    ]
    name: NonEmptyStr
    required: bool
    portable: bool
    rationale: NonEmptyStr


class CapabilityResourceV1(FrozenModel):
    """Content-free inventory entry for one upstream skill resource."""

    resource_version: Literal["1.0.0"] = "1.0.0"
    resource_id: Identifier
    source_id: Identifier
    relative_path: NonEmptyStr
    kind: CapabilityResourceKind
    digest: Sha256Digest
    utf8_bytes: int = Field(ge=0, le=262_144)
    admitted: bool
    admission_reason: NonEmptyStr

    @field_validator("relative_path")
    @classmethod
    def path_is_relative_and_normalized(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("resource paths must stay inside the pinned skill root")
        return normalized

    @model_validator(mode="after")
    def executable_material_is_never_admitted(self) -> Self:
        if self.admitted and self.kind in {
            CapabilityResourceKind.SCRIPT,
            CapabilityResourceKind.HOOK,
            CapabilityResourceKind.DEPENDENCY,
            CapabilityResourceKind.TOOL,
        }:
            raise ValueError("the declarative Foundry policy cannot admit executable resources")
        return self


class CuratedSourceManifestV1(FrozenModel):
    """Immutable identity and content inventory for one upstream skill source."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    source_id: Identifier
    publisher: NonEmptyStr
    repository_url: NonEmptyStr
    commit_sha: NonEmptyStr
    source_path: NonEmptyStr
    source_format: Literal["agent-skill", "codex-plugin-skill", "claude-skill"]
    source_digest: Sha256Digest
    license_spdx: NonEmptyStr
    license_locator: NonEmptyStr
    license_digest: Sha256Digest
    redistribution_permitted: bool
    retrieved_at: UtcDateTime
    resources: tuple[CapabilityResourceV1, ...] = ()
    requirements: tuple[SourceCapabilityRequirementV1, ...] = ()

    @field_validator("repository_url")
    @classmethod
    def repository_is_explicit_https_github_url(cls, value: str) -> str:
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError("the initial Foundry accepts canonical HTTPS GitHub repositories only")
        return value.removesuffix(".git")

    @field_validator("commit_sha")
    @classmethod
    def commit_is_immutable_full_sha(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("source revisions must be full lowercase Git commit SHAs")
        return value

    @field_validator("license_locator", "source_path")
    @classmethod
    def source_paths_are_bounded(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip("/")
        if ".." in normalized.split("/") or not normalized:
            raise ValueError("source locators must stay within the pinned repository")
        return normalized

    @field_validator("source_path")
    @classmethod
    def source_path_names_skill(cls, value: str) -> str:
        if not value.endswith("SKILL.md"):
            raise ValueError("source_path must name one bounded SKILL.md")
        return value

    @field_validator("resources")
    @classmethod
    def resources_are_sorted_unique(
        cls, value: tuple[CapabilityResourceV1, ...]
    ) -> tuple[CapabilityResourceV1, ...]:
        keys = tuple(item.resource_id for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("source resources must be sorted and unique")
        return value

    @field_validator("requirements")
    @classmethod
    def requirements_are_sorted_unique(
        cls, value: tuple[SourceCapabilityRequirementV1, ...]
    ) -> tuple[SourceCapabilityRequirementV1, ...]:
        keys = tuple(item.requirement_id for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("source requirements must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SourceReviewV1(FrozenModel):
    """Deterministic and human-reviewable admission result for one source."""

    review_version: Literal["1.0.0"] = "1.0.0"
    review_id: Identifier
    source_manifest_digest: Sha256Digest
    status: SourceReviewStatus
    license_verified: bool
    provenance_verified: bool
    declarative_only: bool
    static_safety_passed: bool
    findings: tuple[NonEmptyStr, ...] = ()
    reviewed_at: UtcDateTime

    @model_validator(mode="after")
    def reviewed_status_requires_every_gate(self) -> Self:
        gates = (
            self.license_verified,
            self.provenance_verified,
            self.declarative_only,
            self.static_safety_passed,
        )
        if self.status is SourceReviewStatus.REVIEWED and not all(gates):
            raise ValueError("a reviewed source must pass every Foundry admission gate")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeComponentV1(FrozenModel):
    """Exact transformation lineage from upstream source to a Mode clause."""

    component_version: Literal["1.0.0"] = "1.0.0"
    component_id: Identifier
    source_id: Identifier
    source_manifest_digest: Sha256Digest
    source_locator: NonEmptyStr
    disposition: Literal["adapted", "adopted", "omitted"]
    output_clause_ids: tuple[Identifier, ...] = ()
    rationale: NonEmptyStr

    @field_validator("output_clause_ids")
    @classmethod
    def output_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("component output clauses must be sorted and unique")
        return value

    @model_validator(mode="after")
    def omissions_have_no_output(self) -> Self:
        if self.disposition == "omitted" and self.output_clause_ids:
            raise ValueError("omitted components cannot emit Mode clauses")
        if self.disposition != "omitted" and not self.output_clause_ids:
            raise ValueError("included components must emit at least one Mode clause")
        return self


class CuratedModeReleaseV1(FrozenModel):
    """One reviewed Mode composition; effectiveness remains an explicit status."""

    release_schema_version: Literal["1.0.0"] = "1.0.0"
    release_id: Identifier
    mode: CapabilityMode
    source_manifests: Annotated[tuple[CuratedSourceManifestV1, ...], Field(min_length=1)]
    source_reviews: Annotated[tuple[SourceReviewV1, ...], Field(min_length=1)]
    components: Annotated[tuple[ModeComponentV1, ...], Field(min_length=1)]
    evaluation_status: CatalogEvaluationStatus
    evaluation_digest: Sha256Digest | None = None
    known_limitations: tuple[NonEmptyStr, ...] = ()
    released_at: UtcDateTime

    @model_validator(mode="after")
    def lineage_and_evaluation_are_complete(self) -> Self:
        source_ids = {item.source_id for item in self.source_manifests}
        manifest_digests = {item.content_digest for item in self.source_manifests}
        if any(
            item.source_id not in source_ids or item.source_manifest_digest not in manifest_digests
            for item in self.components
        ):
            raise ValueError("every Mode component must bind one exact source manifest")
        review_digests = {item.source_manifest_digest for item in self.source_reviews}
        if review_digests != manifest_digests:
            raise ValueError("every source manifest requires exactly one review lineage")
        emitted = {clause_id for item in self.components for clause_id in item.output_clause_ids}
        if emitted != {item.clause_id for item in self.mode.clauses}:
            raise ValueError("component lineage must cover every emitted Mode clause exactly")
        evaluated = self.evaluation_status is CatalogEvaluationStatus.PRODUCT_EVALUATED
        if evaluated != (self.evaluation_digest is not None):
            raise ValueError("only product-evaluated releases may bind evaluation evidence")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CuratedCatalogManifestV1(FrozenModel):
    """Offline catalog payload distributed with one Temper build."""

    catalog_version: Literal["1.0.0"] = "1.0.0"
    catalog_id: Identifier
    release_version: SemVer
    releases: Annotated[tuple[CuratedModeReleaseV1, ...], Field(min_length=1)]
    generated_at: UtcDateTime

    @field_validator("releases")
    @classmethod
    def releases_are_sorted_unique(
        cls, value: tuple[CuratedModeReleaseV1, ...]
    ) -> tuple[CuratedModeReleaseV1, ...]:
        keys = tuple(item.release_id for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("catalog releases must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SignedCuratedCatalogV1(FrozenModel):
    """Detached catalog signature plus its explicit public verification key."""

    signed_catalog_version: Literal["1.0.0"] = "1.0.0"
    catalog: CuratedCatalogManifestV1
    public_key_base64: NonEmptyStr
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def signature_metadata_is_catalog_specific(self) -> Self:
        if self.signature.purpose != "curated_mode_catalog":
            raise ValueError("catalog signature purpose is inconsistent")
        if self.signature.signed_at != self.catalog.generated_at:
            raise ValueError("catalog signature timestamp is inconsistent")
        return self


class FoundryScreeningTaskV1(FrozenModel):
    """One relevance-bearing task selected before curated Mode inference."""

    task_version: Literal["1.0.0"] = "1.0.0"
    task_id: Identifier
    mode_id: Identifier
    kind: Literal["diagnostic", "neutral_control"]
    prompt_digest: Sha256Digest


class FoundryScreeningCellV1(FrozenModel):
    """One bounded target cell in the three-condition Foundry screen."""

    sequence: Annotated[int, Field(ge=1, le=24)]
    run_id: Identifier
    mode_id: Identifier
    task_id: Identifier
    condition: Literal["compiled_mode", "core_only", "upstream_safe"]


class FoundryScreeningDesignV1(FrozenModel):
    """Small pre-product comparison that cannot itself establish broad effectiveness."""

    design_version: Literal["1.0.0"] = "1.0.0"
    catalog_digest: Sha256Digest
    release_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=3, max_length=3)]
    tasks: Annotated[tuple[FoundryScreeningTaskV1, ...], Field(min_length=9, max_length=9)]
    cells: Annotated[tuple[FoundryScreeningCellV1, ...], Field(min_length=24, max_length=24)]
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["medium"] = "medium"
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    provider_billed_calls: Literal[0] = 0
    per_run_timeout_seconds: Literal[600] = 600
    tuning_after_first_run: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def design_is_complete(self) -> Self:
        if self.release_digests != tuple(sorted(set(self.release_digests))):
            raise ValueError("screening release digests must be sorted and unique")
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("screening tasks must be sorted and unique")
        if tuple(item.sequence for item in self.cells) != tuple(range(1, 25)):
            raise ValueError("screening sequence must be contiguous")
        if len({item.run_id for item in self.cells}) != 24:
            raise ValueError("screening run IDs must be unique")
        for task in self.tasks:
            conditions = {item.condition for item in self.cells if item.task_id == task.task_id}
            expected = (
                {"compiled_mode", "core_only", "upstream_safe"}
                if task.kind == "diagnostic"
                else {"compiled_mode", "core_only"}
            )
            if conditions != expected:
                raise ValueError("each screening task requires its preregistered conditions")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
