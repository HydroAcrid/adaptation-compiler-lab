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
    ACCURACY = "accuracy"
    DATA_PROTECTION = "data_protection"
    DESIGN_SYSTEM = "design_system"
    EVIDENCE = "evidence"
    FAILURE_HANDLING = "failure_handling"
    RESPONSIVE = "responsive"
    SECURITY = "security"
    THREAT_MODEL = "threat_model"
    VALIDATION = "validation"
    VISUAL_DIRECTION = "visual_direction"
    WORKFLOW = "workflow"


class ModeEvaluationStatus(StrEnum):
    """Honest product status; conformance is not effectiveness evidence."""

    EXPERIMENTAL = "experimental"
    FAILED = "failed"
    PRODUCT_EVALUATED = "product_evaluated"


class ModeTargetCompatibility(FrozenModel):
    """One version-pinned target surface for managed Mode delivery."""

    target_family: Identifier
    version_constraint: NonEmptyStr
    delivery_surface: NonEmptyStr


class ModeSecurityPosture(FrozenModel):
    """Explicit capability posture; omission never grants ambient capability."""

    network_access: Literal["not_requested"] = "not_requested"
    executable_content: Literal["forbidden"] = "forbidden"
    tool_installation: Literal["forbidden"] = "forbidden"
    plugin_installation: Literal["forbidden"] = "forbidden"
    mcp_configuration: Literal["forbidden"] = "forbidden"
    dependency_installation: Literal["forbidden"] = "forbidden"


class ModeClause(FrozenModel):
    """One compact default that may be suppressed by a higher-authority claim."""

    clause_id: Identifier
    claim_key: Identifier
    category: ModeClauseCategory
    text: NonEmptyStr


class CapabilityMode(FrozenModel):
    """Versioned first-party expertise kept separate from a user's permanent Core."""

    mode_schema_version: Literal["1.0.0", "1.1.0"] = "1.1.0"
    mode_id: Identifier
    mode_version: SemVer
    name: NonEmptyStr
    summary: NonEmptyStr
    publisher: NonEmptyStr
    source_revision: NonEmptyStr
    source_license: NonEmptyStr
    source_kind: Literal["first_party", "imported"] = "first_party"
    applicable_task_classes: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    compatible_target_families: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    target_compatibility: tuple[ModeTargetCompatibility, ...] = ()
    requested_tools: tuple[Identifier, ...] = ()
    required_capabilities: tuple[Identifier, ...] = ()
    prohibited_implicit_capabilities: tuple[Identifier, ...] = (
        "dependencies",
        "hooks",
        "mcp",
        "network",
        "plugins",
        "scripts",
        "tools",
    )
    security_posture: ModeSecurityPosture = ModeSecurityPosture()
    clauses: Annotated[tuple[ModeClause, ...], Field(min_length=1)]
    maximum_projection_utf8_bytes: int = Field(gt=0, le=3000)
    activation_default: Literal["one_task"] = "one_task"
    task_lease_hours: int = Field(default=4, ge=1, le=24)
    supports_personal_overlay: Literal[True] = True
    evaluation_status: ModeEvaluationStatus = ModeEvaluationStatus.EXPERIMENTAL
    evaluation_digest: Sha256Digest | None = None
    mutates_permanent_core: Literal[False] = False
    auto_activates: Literal[False] = False

    @field_validator(
        "applicable_task_classes",
        "compatible_target_families",
        "requested_tools",
        "required_capabilities",
        "prohibited_implicit_capabilities",
    )
    @classmethod
    def tuple_values_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("mode tuple values must be sorted and unique")
        return value

    @field_validator("target_compatibility")
    @classmethod
    def target_contracts_are_sorted_unique(
        cls, value: tuple[ModeTargetCompatibility, ...]
    ) -> tuple[ModeTargetCompatibility, ...]:
        keys = tuple((item.target_family, item.delivery_surface) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("mode target compatibility must be sorted and unique")
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

    @model_validator(mode="after")
    def capability_and_evaluation_contract_is_explicit(self) -> Self:
        if set(self.required_capabilities).intersection(self.prohibited_implicit_capabilities):
            raise ValueError("a required Mode capability cannot also be prohibited")
        if any(
            item.target_family not in self.compatible_target_families
            for item in self.target_compatibility
        ):
            raise ValueError("mode target contract names an incompatible target family")
        if self.evaluation_status is ModeEvaluationStatus.PRODUCT_EVALUATED:
            if self.evaluation_digest is None:
                raise ValueError("a product-evaluated Mode requires its evaluation digest")
        elif self.evaluation_digest is not None:
            raise ValueError("an unevaluated or failed Mode cannot claim an evaluation digest")
        return self

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


class ModeEvaluationTask(FrozenModel):
    """One public natural task in a same-agent Mode comparison."""

    task_id: Identifier
    kind: Literal["diagnostic", "neutral_control"]
    title: NonEmptyStr
    task_class: Identifier
    brief: NonEmptyStr
    success_checks: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class ModeEvaluationDesignV1(FrozenModel):
    """Frozen zero-provider-billed design; it contains no result claim."""

    design_version: Literal["1.0.0"] = "1.0.0"
    mode_id: Identifier
    mode_version: SemVer
    mode_digest: Sha256Digest
    target_family: Literal["codex"] = "codex"
    comparison_conditions: tuple[Literal["core-only", "core-plus-mode"], ...] = (
        "core-only",
        "core-plus-mode",
    )
    fresh_session_per_trial: Literal[True] = True
    provider_billed_calls: Literal[False] = False
    blinded_secondary_quality_review: Literal[True] = True
    tasks: Annotated[tuple[ModeEvaluationTask, ...], Field(min_length=5, max_length=5)]
    maximum_target_runs: Literal[10] = 10

    @model_validator(mode="after")
    def design_has_three_diagnostics_and_two_controls(self) -> Self:
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("mode evaluation tasks must be sorted and unique")
        diagnostic_count = sum(item.kind == "diagnostic" for item in self.tasks)
        neutral_count = sum(item.kind == "neutral_control" for item in self.tasks)
        if diagnostic_count != 3 or neutral_count != 2:
            raise ValueError("mode evaluation requires three diagnostics and two neutral controls")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
