"""Typed records for temporary, task-scoped capability Modes."""

from __future__ import annotations

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
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.base import sha256_text


class ModeClauseCategory(StrEnum):
    """Bounded kinds of expertise a Mode may add to one task."""

    ACCESSIBILITY = "accessibility"
    DESIGN_SYSTEM = "design_system"
    RESPONSIVE = "responsive"
    VALIDATION = "validation"
    VISUAL_DIRECTION = "visual_direction"
    WORKFLOW = "workflow"


class ModeClause(FrozenModel):
    """One compact default that may be suppressed by a higher-authority claim."""

    clause_id: Identifier
    claim_key: Identifier
    category: ModeClauseCategory
    text: NonEmptyStr


class CapabilityMode(FrozenModel):
    """Versioned first-party expertise kept separate from a user's permanent Core."""

    mode_schema_version: Literal["1.0.0"] = "1.0.0"
    mode_id: Identifier
    mode_version: SemVer
    name: NonEmptyStr
    summary: NonEmptyStr
    publisher: NonEmptyStr
    source_revision: NonEmptyStr
    source_license: NonEmptyStr
    applicable_task_classes: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    compatible_target_families: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    requested_tools: tuple[Identifier, ...] = ()
    clauses: Annotated[tuple[ModeClause, ...], Field(min_length=1)]
    maximum_projection_utf8_bytes: int = Field(gt=0, le=3000)
    activation_default: Literal["one_task"] = "one_task"
    mutates_permanent_core: Literal[False] = False

    @field_validator("applicable_task_classes", "compatible_target_families", "requested_tools")
    @classmethod
    def tuple_values_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("mode tuple values must be sorted and unique")
        return value

    @field_validator("clauses")
    @classmethod
    def clauses_are_sorted_unique(cls, value: tuple[ModeClause, ...]) -> tuple[ModeClause, ...]:
        keys = tuple((item.claim_key, item.clause_id) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("mode clauses must be sorted and unique")
        if len({item.claim_key for item in value}) != len(value):
            raise ValueError("mode claim keys must be unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeActivationReceipt(FrozenModel):
    """Signed exact-task lease; it is not a permanent preference mutation."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    activation_id: Identifier
    subject_id: Identifier
    mode_id: Identifier
    mode_version: SemVer
    mode_digest: Sha256Digest
    project_id: Identifier
    task_digest: Sha256Digest
    target_family: Identifier
    prior_core_release_digest: Sha256Digest
    suppressed_claim_keys: tuple[Identifier, ...] = ()
    activated_at: UtcDateTime
    expires_at: UtcDateTime
    ends_after_task: Literal[True] = True
    signature: SignatureEnvelope

    @field_validator("suppressed_claim_keys")
    @classmethod
    def suppressed_keys_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("suppressed mode claim keys must be sorted and unique")
        return value

    @model_validator(mode="after")
    def lease_is_bounded(self) -> Self:
        if self.expires_at <= self.activated_at:
            raise ValueError("mode activation must expire after it starts")
        if (
            self.signature.purpose != "mode_activation"
            or self.signature.signed_at != self.activated_at
        ):
            raise ValueError("mode activation signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeDeliveryReceipt(FrozenModel):
    """Signed binding from the temporary lease to the exact delivered task text."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    activation_digest: Sha256Digest
    base_delivery_digest: Sha256Digest
    mode_material_digest: Sha256Digest
    combined_delivery_digest: Sha256Digest
    mode_material_utf8_bytes: int = Field(gt=0, le=3000)
    delivered_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def signature_metadata_matches(self) -> Self:
        if (
            self.signature.purpose != "mode_delivery"
            or self.signature.signed_at != self.delivered_at
        ):
            raise ValueError("mode delivery signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModePreparedTask(FrozenModel):
    """Transient composed task; raw task text never enters a durable mode receipt."""

    delivered_task: NonEmptyStr
    mode_material: NonEmptyStr
    included_clause_ids: tuple[Identifier, ...]
    activation: ModeActivationReceipt
    delivery: ModeDeliveryReceipt

    @model_validator(mode="after")
    def material_occurs_once_and_digests_match(self) -> Self:
        if self.delivered_task.count(self.mode_material) != 1:
            raise ValueError("mode material must occur exactly once")
        if sha256_text(self.delivered_task) != self.delivery.combined_delivery_digest:
            raise ValueError("combined mode delivery digest changed")
        if sha256_text(self.mode_material) != self.delivery.mode_material_digest:
            raise ValueError("mode material digest changed")
        if self.delivery.activation_digest != self.activation.content_digest:
            raise ValueError("mode delivery does not bind its activation")
        return self


class ModeDeactivationReceipt(FrozenModel):
    """Signed proof that task completion restored the exact prior Core release."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    activation_digest: Sha256Digest
    delivery_digest: Sha256Digest
    outcome: Literal["completed", "failed", "cancelled"]
    restored_core_release_digest: Sha256Digest
    deactivated_at: UtcDateTime
    mode_clauses_remaining: Literal[0] = 0
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def signature_metadata_matches(self) -> Self:
        if (
            self.signature.purpose != "mode_deactivation"
            or self.signature.signed_at != self.deactivated_at
        ):
            raise ValueError("mode deactivation signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeEvaluationCaseResult(FrozenModel):
    case_id: Identifier
    passed: bool
    check: NonEmptyStr


class ModeEvaluationReport(FrozenModel):
    """Deterministic conformance report, not a claim of agent-performance uplift."""

    report_version: Literal["1.0.0"] = "1.0.0"
    mode_digest: Sha256Digest
    cases: Annotated[tuple[ModeEvaluationCaseResult, ...], Field(min_length=1)]
    relevant_cases_passed: int = Field(ge=0)
    neutral_controls_passed: int = Field(ge=0)
    projection_utf8_bytes: int = Field(gt=0)
    valid: bool

    @model_validator(mode="after")
    def counts_and_validity_are_exact(self) -> Self:
        case_ids = tuple(item.case_id for item in self.cases)
        if case_ids != tuple(sorted(set(case_ids))):
            raise ValueError("mode evaluation cases must be sorted and unique")
        if self.valid != all(item.passed for item in self.cases):
            raise ValueError("mode evaluation validity must equal all case outcomes")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
