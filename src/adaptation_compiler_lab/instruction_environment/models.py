"""Strict records for native instruction environments.

Native files are contextual inputs. These records intentionally do not use Evidence or Artifact
types: observing a repository instruction never grants it user authority or makes it portable.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.serialization import canonical_digest


class NativeTarget(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"
    COPILOT = "copilot"


class NativeSourceKind(StrEnum):
    PROJECT_INSTRUCTIONS = "project_instructions"
    PROJECT_RULE = "project_rule"
    PROJECT_SKILL = "project_skill"
    PERSONAL_INSTRUCTIONS = "personal_instructions"
    PERSONAL_MEMORY = "personal_memory"
    PERSONAL_SKILL = "personal_skill"
    MANAGED_INSTRUCTIONS = "managed_instructions"


class NativeAuthorityClass(StrEnum):
    MANAGED_POLICY = "managed_policy"
    PROJECT_POLICY = "project_policy"
    USER_CONFIGURED = "user_configured"
    AGENT_GENERATED = "agent_generated"


class NativeReadStatus(StrEnum):
    READY = "ready"
    UNREADABLE = "unreadable"
    INVALID_ENCODING = "invalid_encoding"
    TOO_LARGE = "too_large"
    OUTSIDE_BOUNDARY = "outside_boundary"
    UNSUPPORTED = "unsupported"


class NativeActivationStatus(StrEnum):
    ACTIVE = "active"
    AVAILABLE = "available"
    DISABLED = "disabled"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class NativeInstructionKind(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    NORM = "norm"
    PROCEDURE = "procedure"
    EXAMPLE = "example"
    EXCEPTION = "exception"
    CAPABILITY = "capability"
    UNKNOWN = "unknown"


class NativeNormStrength(StrEnum):
    NONE = "none"
    PREFERENCE = "preference"
    INVARIANT = "invariant"


class InstructionRelationKind(StrEnum):
    EXACT_DUPLICATE = "exact_duplicate"
    SEMANTIC_EQUIVALENT = "semantic_equivalent"
    CONTRADICTION = "contradiction"
    NARROWER_EXCEPTION = "narrower_exception"
    BROADER_OVERLAP = "broader_overlap"
    COMPLEMENTARY = "complementary"
    UNKNOWN = "unknown"


class InstructionResolution(StrEnum):
    OMIT_TEMPER = "omit_temper"
    INCLUDE_TEMPER = "include_temper"
    PRESERVE_SCOPED = "preserve_scoped"
    BLOCK_TEMPER = "block_temper"
    NEEDS_REVIEW = "needs_review"


class InstructionSourceManifestV1(FrozenModel):
    """Raw-free metadata for one exact native source."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    source_id: Identifier
    target: NativeTarget
    surface: NonEmptyStr
    surface_contract_version: NonEmptyStr
    source_kind: NativeSourceKind
    display_path: NonEmptyStr
    project_id: Identifier | None = None
    native_precedence: int = Field(ge=0)
    authority_class: NativeAuthorityClass
    opt_in_basis: Literal["registered_project", "explicit_global_opt_in", "managed"]
    content_digest: Sha256Digest | None = None
    byte_length: int = Field(ge=0)
    encoding: Literal["utf-8", "utf-8-sig", "unknown"]
    newline_style: Literal["lf", "crlf", "mixed", "none", "unknown"]
    read_status: NativeReadStatus
    symlink: bool
    resolved_within_boundary: bool
    contains_executable_resources: bool = False
    activation_status: NativeActivationStatus = NativeActivationStatus.NOT_APPLICABLE
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def readable_metadata_is_complete(self) -> Self:
        if self.read_status is NativeReadStatus.READY:
            if self.content_digest is None or self.encoding == "unknown":
                raise ValueError("readable native source requires digest and encoding")
            if not self.resolved_within_boundary:
                raise ValueError("readable native source must remain inside its boundary")
        elif self.content_digest is not None:
            raise ValueError("unreadable native source cannot claim a content digest")
        if self.opt_in_basis == "registered_project" and self.project_id is None:
            raise ValueError("registered-project source requires a project ID")
        is_skill = self.source_kind in {
            NativeSourceKind.PERSONAL_SKILL,
            NativeSourceKind.PROJECT_SKILL,
        }
        if is_skill and self.activation_status is NativeActivationStatus.NOT_APPLICABLE:
            raise ValueError("native skill activation status is inconsistent")
        if not is_skill and self.activation_status is not NativeActivationStatus.ACTIVE:
            raise ValueError("native instruction activation status is inconsistent")
        return self


class NativeInstructionClauseV1(FrozenModel):
    """Internal normalized clause with exact native lineage.

    ``text`` is never returned through a raw-free desktop summary. If cached, this complete record
    must be encrypted under the local raw-store key.
    """

    clause_version: Literal["1.0.0"] = "1.0.0"
    clause_id: Identifier
    text: NonEmptyStr
    text_digest: Sha256Digest
    source_id: Identifier
    source_digest: Sha256Digest
    target: NativeTarget
    kind: NativeInstructionKind = NativeInstructionKind.UNKNOWN
    norm_strength: NativeNormStrength = NativeNormStrength.NONE
    scope_labels: tuple[NonEmptyStr, ...] = ()
    polarity: Literal["positive", "negative", "neutral"] = "neutral"
    explicit_exception: bool = False
    semantic_confidence: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    interpreter_digest: Sha256Digest | None = None

    @field_validator("scope_labels")
    @classmethod
    def scopes_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("native clause scope labels must be sorted and unique")
        return value

    @model_validator(mode="after")
    def digest_matches_text(self) -> Self:
        if canonical_digest({"text": self.text}) != self.text_digest:
            raise ValueError("native clause text digest changed")
        if self.semantic_confidence > 0 and self.interpreter_digest is None:
            raise ValueError("semantic classification requires an interpreter digest")
        return self


class InstructionEnvironmentSnapshotV1(FrozenModel):
    """Exact contextual instruction environment for one target and project."""

    snapshot_version: Literal["1.0.0"] = "1.0.0"
    project_id: Identifier
    target: NativeTarget
    surface: NonEmptyStr
    surface_contract_version: NonEmptyStr
    source_manifests: tuple[InstructionSourceManifestV1, ...]
    clauses: tuple[NativeInstructionClauseV1, ...]
    complete: bool
    issues: tuple[NonEmptyStr, ...] = ()
    generated_at: UtcDateTime
    global_sources_enabled: bool = False

    @field_validator("source_manifests")
    @classmethod
    def sources_are_ordered_unique(
        cls, value: tuple[InstructionSourceManifestV1, ...]
    ) -> tuple[InstructionSourceManifestV1, ...]:
        keys = tuple((item.native_precedence, item.source_id) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("native sources must be precedence-ordered and unique")
        return value

    @field_validator("clauses")
    @classmethod
    def clauses_are_unique(
        cls, value: tuple[NativeInstructionClauseV1, ...]
    ) -> tuple[NativeInstructionClauseV1, ...]:
        ids = tuple(item.clause_id for item in value)
        if ids != tuple(dict.fromkeys(ids)):
            raise ValueError("native clauses must be unique")
        return value

    @model_validator(mode="after")
    def lineage_is_local(self) -> Self:
        if any(
            item.target is not self.target
            or item.surface != self.surface
            or item.surface_contract_version != self.surface_contract_version
            for item in self.source_manifests
        ):
            raise ValueError("native source manifest crossed its target surface")
        sources = {
            item.source_id: item.content_digest
            for item in self.source_manifests
            if item.read_status is NativeReadStatus.READY
        }
        if any(sources.get(item.source_id) != item.source_digest for item in self.clauses):
            raise ValueError("native clause does not bind an exact readable source")
        if self.complete != all(
            item.read_status is NativeReadStatus.READY for item in self.source_manifests
        ):
            raise ValueError("instruction-environment completeness is inconsistent")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json", exclude={"generated_at"}))

    @property
    def source_chain_digest(self) -> Sha256Digest:
        return canonical_digest(
            {
                "project_id": self.project_id,
                "surface": self.surface,
                "surface_contract_version": self.surface_contract_version,
                "target": self.target.value,
                "sources": [
                    {
                        "content_digest": item.content_digest,
                        "native_precedence": item.native_precedence,
                        "source_id": item.source_id,
                    }
                    for item in self.source_manifests
                ],
            }
        )


class InstructionRelationV1(FrozenModel):
    relation_version: Literal["1.0.0"] = "1.0.0"
    temper_clause_digest: Sha256Digest
    native_clause_id: Identifier
    native_clause_digest: Sha256Digest
    relation: InstructionRelationKind
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    deterministic: bool
    resolution: InstructionResolution
    rationale: NonEmptyStr
    interpreter_digests: tuple[Sha256Digest, ...] = ()

    @field_validator("interpreter_digests")
    @classmethod
    def interpreter_digests_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("interpreter digests must be sorted and unique")
        return value

    @model_validator(mode="after")
    def model_relations_have_receipts(self) -> Self:
        if not self.deterministic and not self.interpreter_digests:
            raise ValueError("semantic relation requires interpreter receipts")
        return self


class InstructionConflictV1(FrozenModel):
    conflict_version: Literal["1.0.0"] = "1.0.0"
    conflict_id: Identifier
    project_id: Identifier
    target: NativeTarget
    temper_clause_digest: Sha256Digest
    native_clause_id: Identifier
    native_source_id: Identifier
    relation: InstructionRelationKind
    native_precedence: int = Field(ge=0)
    severity: Literal["notice", "blocking"]
    resolution_state: Literal["unresolved", "kept_native", "narrowed_temper", "ignored"]
    rationale: NonEmptyStr


class InstructionDeltaPlanV1(FrozenModel):
    plan_version: Literal["1.0.0"] = "1.0.0"
    project_id: Identifier
    target: NativeTarget
    surface: NonEmptyStr
    surface_contract_version: NonEmptyStr
    environment_digest: Sha256Digest
    source_chain_digest: Sha256Digest
    included_temper_clause_digests: tuple[Sha256Digest, ...]
    omitted_temper_clause_digests: tuple[Sha256Digest, ...]
    blocked_temper_clause_digests: tuple[Sha256Digest, ...]
    relations: tuple[InstructionRelationV1, ...]
    conflicts: tuple[InstructionConflictV1, ...]
    input_utf8_bytes: int = Field(ge=0)
    output_utf8_bytes: int = Field(ge=0)
    fully_optimized: bool

    @field_validator(
        "included_temper_clause_digests",
        "omitted_temper_clause_digests",
        "blocked_temper_clause_digests",
    )
    @classmethod
    def digest_sets_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("delta-plan clause digests must be sorted and unique")
        return value

    @model_validator(mode="after")
    def clause_sets_do_not_overlap(self) -> Self:
        sets = (
            set(self.included_temper_clause_digests),
            set(self.omitted_temper_clause_digests),
            set(self.blocked_temper_clause_digests),
        )
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            raise ValueError("delta-plan clause dispositions overlap")
        if self.output_utf8_bytes > self.input_utf8_bytes:
            raise ValueError("native-aware delta cannot exceed the unaware projection")
        return self


class InstructionSourceSummaryV1(FrozenModel):
    summary_version: Literal["1.0.0"] = "1.0.0"
    source_id: Identifier
    target: NativeTarget
    kind: NativeSourceKind
    display_path: NonEmptyStr
    scope_summary: NonEmptyStr
    status: NativeReadStatus
    instruction_count: int = Field(ge=0)
    skill: bool
    activation_status: NativeActivationStatus
    observed_context_only: Literal[True] = True
    raw_payloads_exposed: Literal[False] = False


class InstructionConflictSummaryV1(FrozenModel):
    summary_version: Literal["1.0.0"] = "1.0.0"
    conflict_id: Identifier
    project_id: Identifier
    target: NativeTarget
    source_display_path: NonEmptyStr
    temper_behavior: str = Field(min_length=1, max_length=500)
    native_behavior: str = Field(min_length=1, max_length=500)
    severity: Literal["notice", "blocking"]
    resolution_state: Literal["unresolved", "kept_native", "narrowed_temper", "ignored"]
    rationale: str = Field(min_length=1, max_length=500)
    raw_payloads_exposed: Literal[False] = False


class InstructionEnvironmentSummaryV1(FrozenModel):
    summary_version: Literal["1.0.0"] = "1.0.0"
    project_id: Identifier
    target: NativeTarget
    status: Literal["understood", "changed", "incomplete", "conflicting"]
    source_count: int = Field(ge=0)
    skill_count: int = Field(ge=0)
    instruction_count: int = Field(ge=0)
    blocking_conflict_count: int = Field(ge=0)
    semantic_analysis_status: Literal["not_requested", "current", "stale", "unavailable"]
    last_analyzed_at: UtcDateTime
    environment_digest: Sha256Digest
    source_chain_digest: Sha256Digest
    surface: NonEmptyStr
    surface_contract_version: NonEmptyStr
    global_sources_enabled: bool
    sources: tuple[InstructionSourceSummaryV1, ...]
    conflicts: tuple[InstructionConflictSummaryV1, ...] = ()
    raw_payloads_exposed: Literal[False] = False


class InstructionGlobalPreviewV1(FrozenModel):
    preview_version: Literal["1.0.0"] = "1.0.0"
    preview_token: Identifier
    target: NativeTarget
    categories: tuple[NonEmptyStr, ...]
    source_count: int = Field(ge=0)
    skill_count: int = Field(ge=0)
    modifies_files: Literal[False] = False
    authorizes_learning: Literal[False] = False
    expires_at: UtcDateTime
    raw_payloads_exposed: Literal[False] = False


class NativeInstructionChangePreviewV1(FrozenModel):
    preview_version: Literal["1.0.0"] = "1.0.0"
    preview_token: Identifier
    project_id: Identifier
    target: NativeTarget
    source_id: Identifier
    source_digest: Sha256Digest
    expected_environment_digest: Sha256Digest
    operation: Literal["create_temper_section", "update_temper_section", "remove_temper_section"]
    display_path: NonEmptyStr
    unified_diff: NonEmptyStr
    resulting_digest: Sha256Digest
    expires_at: UtcDateTime
    raw_payloads_exposed: Literal[False] = False


class NativeInstructionChangeReceiptV1(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    preview_token: Identifier
    project_id: Identifier
    target: NativeTarget
    source_id: Identifier
    before_digest: Sha256Digest
    after_digest: Sha256Digest
    environment_digest_before: Sha256Digest
    environment_digest_after: Sha256Digest
    backup_digest: Sha256Digest
    applied_at: UtcDateTime
    signer_fingerprint: Sha256Digest
    signature_base64: NonEmptyStr
    rollback_available_until: UtcDateTime
    status: Literal["applied", "rolled_back"] = "applied"
    rollback_of_receipt_id: Identifier | None = None
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def rollback_lineage_is_explicit(self) -> Self:
        if (self.status == "rolled_back") != (self.rollback_of_receipt_id is not None):
            raise ValueError("native rollback receipt lineage is inconsistent")
        return self


TemperClauseText = Annotated[str, Field(min_length=1, max_length=32_768)]

# Transitional names retained for the already-shipped desktop protocol. The canonical schema
# titles and new code use the explicit ``NativeInstruction*`` names from the interoperability
# contract.
InstructionChangePreviewV1 = NativeInstructionChangePreviewV1
InstructionChangeReceiptV1 = NativeInstructionChangeReceiptV1
