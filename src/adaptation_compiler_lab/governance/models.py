"""Signed governance contracts for identity, consent, capture, and audited actions."""

from __future__ import annotations

import base64
import hashlib
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.models import (
    BenchmarkCondition,
    BlindConditionId,
    BlindFamilyId,
    BlindTaskId,
    FeasibilityDesign,
    InternalFeasibilityDesign,
    TaskStratum,
)
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import PermittedUse
from adaptation_compiler_lab.domain.references import (
    AdjudicationRecordRef,
    BenchmarkRegistrationRef,
    ConditionMaterialReceiptRef,
    ConsentReceiptRef,
    CustodyAccessEventRef,
    CustodyManifestRef,
    DependencyImpactRef,
    InvalidationEventRef,
    TombstoneReceiptRef,
    TrialResultRef,
)
from adaptation_compiler_lab.domain.values import Scope, strings_are_sorted_unique
from adaptation_compiler_lab.serialization.canonical import canonical_digest

GovernanceSchemaVersion = Literal["1.0"]
CanonicalizationVersion = Literal["1.0.0"]


class GovernanceObjectKind(StrEnum):
    SIGNER_IDENTITY = "signer_identity"
    CONSENT_RECEIPT = "consent_receipt"
    CAPTURE_RECEIPT = "capture_receipt"
    GOVERNANCE_EVENT = "governance_event"
    DEPENDENCY_IMPACT = "dependency_impact"
    INVALIDATION_EVENT = "invalidation_event"
    TOMBSTONE_RECEIPT = "tombstone_receipt"
    RECALL_REPORT = "recall_report"
    CUSTODY_MANIFEST = "custody_manifest"
    BENCHMARK_REGISTRATION = "benchmark_registration"
    CONDITION_MATERIAL_RECEIPT = "condition_material_receipt"
    TRIAL_RESULT = "trial_result"
    ADJUDICATION_RECORD = "adjudication_record"
    CUSTODY_ACCESS_EVENT = "custody_access_event"


class SignerRole(StrEnum):
    CONSENT = "consent"
    REVIEW = "review"
    RELEASE = "release"
    ACTIVATION = "activation"
    CUSTODY = "custody"


class GovernanceEventType(StrEnum):
    REVIEW_DECISION = "review_decision"
    RELEASE_DECISION = "release_decision"
    ACTIVATION_DECISION = "activation_decision"
    CUSTODY_ACTION = "custody_action"


class RecallTargetKind(StrEnum):
    CONSENT_RECEIPT = "consent_receipt"
    CAPTURE_RECEIPT = "capture_receipt"
    TASK_RECORD = "task_record"
    OUTCOME = "outcome"
    EVIDENCE = "evidence"
    EVALUATION_CASE = "evaluation_case"
    LESSON_CANDIDATE = "lesson_candidate"
    ARTIFACT = "artifact"
    RELEASE = "release"
    TARGET_PACK = "target_pack"
    ACTIVATION = "activation"


class InvalidationAction(StrEnum):
    REVOKE_CONSENT = "revoke_consent"
    RESTRICT_EVIDENCE = "restrict_evidence"
    PURGE_EVIDENCE = "purge_evidence"
    REVOKE_ARTIFACT = "revoke_artifact"
    RETIRE_RELEASE = "retire_release"
    INVALIDATE_TARGET_PACK = "invalidate_target_pack"
    EXCLUDE_DEPENDENCY = "exclude_dependency"
    DEACTIVATE_ACTIVATION = "deactivate_activation"


class ConditionConstructionMethod(StrEnum):
    NONE = "none"
    DETERMINISTIC_APPROVED_FEEDBACK = "deterministic_approved_feedback"
    INDEPENDENT_HUMAN_PROFILE = "independent_human_profile"
    ISOLATED_AI_TWO_PASS_PROFILE = "isolated_ai_two_pass_profile"
    COMPILED_RELEASE_PACK = "compiled_release_pack"


class ConditionAuthorRole(StrEnum):
    NONE = "none"
    DETERMINISTIC_RENDERER = "deterministic_renderer"
    INDEPENDENT_HUMAN = "independent_human"
    ISOLATED_AI = "isolated_ai"
    COMPILER = "compiler"


class CustodyAccessAction(StrEnum):
    SEAL = "seal"
    VERIFY = "verify"
    REQUEST_REVEAL = "request_reveal"


class CustodyAccessOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class TrialValidity(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class AdjudicationDecision(StrEnum):
    UPHOLD = "uphold"
    ANNOTATE = "annotate"
    EXCLUDE_FROM_ANALYSIS = "exclude_from_analysis"
    CORRECT_DERIVED_VALUE = "correct_derived_value"


class AdjudicatedField(StrEnum):
    VALIDITY = "validity"
    AUTOMATED_CORRECTNESS = "automated_correctness"
    REQUIREMENT_COVERAGE = "requirement_coverage"
    CHANGE_DISCIPLINE = "change_discipline"
    GUARDRAILS = "guardrails"


class SignatureEnvelope(FrozenModel):
    """Detached Ed25519 signature metadata included in a signed object."""

    algorithm: Literal["Ed25519"] = "Ed25519"
    canonicalization_version: CanonicalizationVersion = "1.0.0"
    signer_identity_id: Identifier
    key_fingerprint: Sha256Digest
    purpose: NonEmptyStr
    signed_at: UtcDateTime
    signature_base64: NonEmptyStr

    @field_validator("signature_base64")
    @classmethod
    def signature_is_raw_ed25519(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except ValueError as error:
            raise ValueError("signature must be canonical base64") from error
        if len(decoded) != 64:
            raise ValueError("Ed25519 signature must contain exactly 64 bytes")
        if base64.b64encode(decoded).decode("ascii") != value:
            raise ValueError("signature must use canonical base64 encoding")
        return value


class SourceSelector(FrozenModel):
    """Explicit bounded source selection; content never widens this selector."""

    source_system: Literal[
        "synthetic_fixture",
        "codex_app_server",
        "local_interaction_runtime",
    ]
    selection_method: Literal["synthetic_fixture", "explicit_task_ids"]
    source_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("source IDs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def selector_method_matches_source(self) -> SourceSelector:
        synthetic = self.source_system == "synthetic_fixture"
        if synthetic != (self.selection_method == "synthetic_fixture"):
            raise ValueError("synthetic selectors must use the synthetic_fixture method")
        return self


class SignerIdentity(FrozenModel):
    """Self-signed public identity for one dedicated local Ed25519 key."""

    governance_type: Literal[GovernanceObjectKind.SIGNER_IDENTITY] = (
        GovernanceObjectKind.SIGNER_IDENTITY
    )
    identity_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    public_key_base64: NonEmptyStr
    key_fingerprint: Sha256Digest
    roles: Annotated[tuple[SignerRole, ...], Field(min_length=1)]
    created_at: UtcDateTime
    expires_at: UtcDateTime | None = None
    signature: SignatureEnvelope

    @field_validator("public_key_base64")
    @classmethod
    def public_key_is_raw_ed25519(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except ValueError as error:
            raise ValueError("public key must be canonical base64") from error
        if len(decoded) != 32:
            raise ValueError("Ed25519 public key must contain exactly 32 bytes")
        if base64.b64encode(decoded).decode("ascii") != value:
            raise ValueError("public key must use canonical base64 encoding")
        return value

    @field_validator("roles")
    @classmethod
    def roles_are_sorted_unique(cls, value: tuple[SignerRole, ...]) -> tuple[SignerRole, ...]:
        raw = tuple(role.value for role in value)
        if not strings_are_sorted_unique(raw):
            raise ValueError("signer roles must be sorted and unique")
        return value

    @model_validator(mode="after")
    def identity_window_and_signature_match(self) -> SignerIdentity:
        raw_public_key = base64.b64decode(self.public_key_base64, validate=True)
        expected_fingerprint = f"sha256:{hashlib.sha256(raw_public_key).hexdigest()}"
        if self.key_fingerprint != expected_fingerprint:
            raise ValueError("identity fingerprint does not match its public key")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("identity expiry must follow creation")
        if self.signature.signer_identity_id != self.identity_id:
            raise ValueError("identity must be self-signed")
        if self.signature.key_fingerprint != self.key_fingerprint:
            raise ValueError("identity signature fingerprint mismatch")
        if self.signature.purpose != "signer_identity":
            raise ValueError("identity signature has the wrong purpose")
        if self.signature.signed_at != self.created_at:
            raise ValueError("identity signature time must equal identity creation time")
        return self


class ConsentReceipt(FrozenModel):
    """Signed permission for a subject, exact selector, uses, scope, and time bounds."""

    governance_type: Literal[GovernanceObjectKind.CONSENT_RECEIPT] = (
        GovernanceObjectKind.CONSENT_RECEIPT
    )
    receipt_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    source_selector: SourceSelector
    scope: Scope
    permitted_uses: Annotated[tuple[PermittedUse, ...], Field(min_length=1)]
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    retention_until: UtcDateTime
    policy_version: SemVer
    signature: SignatureEnvelope

    @field_validator("permitted_uses")
    @classmethod
    def uses_are_sorted_unique(cls, value: tuple[PermittedUse, ...]) -> tuple[PermittedUse, ...]:
        raw = tuple(item.value for item in value)
        if not strings_are_sorted_unique(raw):
            raise ValueError("permitted uses must be sorted and unique")
        return value

    @model_validator(mode="after")
    def consent_is_bounded_and_signed(self) -> ConsentReceipt:
        if self.scope.subject_ids != (self.subject_id,):
            raise ValueError("consent scope must contain exactly its subject")
        if self.expires_at <= self.issued_at:
            raise ValueError("consent expiry must follow issuance")
        if self.retention_until < self.expires_at:
            raise ValueError("retention deadline cannot precede consent expiry")
        if self.signature.purpose != "consent_receipt":
            raise ValueError("consent signature has the wrong purpose")
        if self.signature.signed_at != self.issued_at:
            raise ValueError("consent signature time must equal issuance time")
        return self


class CaptureReceipt(FrozenModel):
    """Signed record of a payload capture or synthetic capture preview."""

    governance_type: Literal[GovernanceObjectKind.CAPTURE_RECEIPT] = (
        GovernanceObjectKind.CAPTURE_RECEIPT
    )
    receipt_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    consent_ref: ConsentReceiptRef
    source_selector: SourceSelector
    source_version: NonEmptyStr
    source_schema_digest: Sha256Digest
    payload_digest: Sha256Digest
    captured_at: UtcDateTime
    synthetic: bool
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def capture_is_signed_and_classified(self) -> CaptureReceipt:
        if self.synthetic != (self.source_selector.source_system == "synthetic_fixture"):
            raise ValueError("capture synthetic flag must match its source selector")
        if self.signature.purpose != "capture_receipt":
            raise ValueError("capture signature has the wrong purpose")
        if self.signature.signed_at != self.captured_at:
            raise ValueError("capture signature time must equal capture time")
        return self


class GovernanceEvent(FrozenModel):
    """Signed review, release, activation, or custody action."""

    governance_type: Literal[GovernanceObjectKind.GOVERNANCE_EVENT] = (
        GovernanceObjectKind.GOVERNANCE_EVENT
    )
    event_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    event_type: GovernanceEventType
    target_ref: NonEmptyStr
    target_digest: Sha256Digest
    decision: NonEmptyStr
    reason: NonEmptyStr
    policy_version: SemVer
    occurred_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def event_signature_matches_kind(self) -> GovernanceEvent:
        expected = {
            GovernanceEventType.REVIEW_DECISION: "review",
            GovernanceEventType.RELEASE_DECISION: "release",
            GovernanceEventType.ACTIVATION_DECISION: "activation",
            GovernanceEventType.CUSTODY_ACTION: "custody",
        }[self.event_type]
        if self.signature.purpose != expected:
            raise ValueError("governance-event signature has the wrong purpose")
        if self.signature.signed_at != self.occurred_at:
            raise ValueError("event signature time must equal occurrence time")
        return self


_RECORD_TARGET_KINDS = {
    RecallTargetKind.TASK_RECORD,
    RecallTargetKind.OUTCOME,
    RecallTargetKind.EVIDENCE,
    RecallTargetKind.EVALUATION_CASE,
    RecallTargetKind.LESSON_CANDIDATE,
    RecallTargetKind.ARTIFACT,
    RecallTargetKind.RELEASE,
    RecallTargetKind.TARGET_PACK,
}


class RecallTarget(FrozenModel):
    """Exact governance, record-version, or activation-head target."""

    target_kind: RecallTargetKind
    object_id: Identifier
    record_version: SemVer | None = None
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def version_matches_target_kind(self) -> RecallTarget:
        is_record = self.target_kind in _RECORD_TARGET_KINDS
        if is_record != (self.record_version is not None):
            raise ValueError(
                "record targets require a version; governance/activation targets do not"
            )
        return self


class ImpactEntry(FrozenModel):
    """One exact node affected by a requested invalidation cascade."""

    target: RecallTarget
    planned_action: InvalidationAction
    distance: int = Field(ge=0)
    relations: tuple[NonEmptyStr, ...] = ()
    current_state: NonEmptyStr | None = None
    head_event_id: Identifier | None = None

    @field_validator("relations")
    @classmethod
    def relations_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("impact relations must be sorted and unique")
        return value


class PayloadImpact(FrozenModel):
    """Minimal metadata for encrypted payload bytes selected for deletion."""

    payload_digest: Sha256Digest
    byte_length: int = Field(ge=0)
    media_type: NonEmptyStr
    locator_digest: Sha256Digest
    evidence_targets: Annotated[tuple[RecallTarget, ...], Field(min_length=1)]

    @field_validator("evidence_targets")
    @classmethod
    def evidence_targets_are_sorted_unique(
        cls, value: tuple[RecallTarget, ...]
    ) -> tuple[RecallTarget, ...]:
        keys = tuple(_recall_target_key(item) for item in value)
        if list(keys) != sorted(set(keys)):
            raise ValueError("payload evidence targets must be sorted and unique")
        if any(item.target_kind is not RecallTargetKind.EVIDENCE for item in value):
            raise ValueError("payload impacts can reference only Evidence targets")
        return value


class DependencyImpact(FrozenModel):
    """Signed, confirmation-bound snapshot of every affected dependency."""

    governance_type: Literal[GovernanceObjectKind.DEPENDENCY_IMPACT] = (
        GovernanceObjectKind.DEPENDENCY_IMPACT
    )
    impact_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    root_target: RecallTarget
    requested_action: InvalidationAction
    affected: Annotated[tuple[ImpactEntry, ...], Field(min_length=1)]
    payloads: tuple[PayloadImpact, ...] = ()
    graph_snapshot_digest: Sha256Digest
    generated_at: UtcDateTime
    policy_version: SemVer
    signature: SignatureEnvelope

    @field_validator("affected")
    @classmethod
    def affected_is_sorted_unique(cls, value: tuple[ImpactEntry, ...]) -> tuple[ImpactEntry, ...]:
        keys = tuple(_recall_target_key(item.target) for item in value)
        if list(keys) != sorted(set(keys)):
            raise ValueError("dependency impact targets must be sorted and unique")
        return value

    @field_validator("payloads")
    @classmethod
    def payloads_are_sorted_unique(
        cls, value: tuple[PayloadImpact, ...]
    ) -> tuple[PayloadImpact, ...]:
        keys = tuple(item.payload_digest for item in value)
        if list(keys) != sorted(set(keys)):
            raise ValueError("payload impacts must be sorted and unique")
        return value

    @model_validator(mode="after")
    def impact_is_complete_and_signed(self) -> DependencyImpact:
        roots = [item for item in self.affected if item.target == self.root_target]
        if len(roots) != 1 or roots[0].distance != 0:
            raise ValueError("dependency impact must contain its root at distance zero")
        if roots[0].planned_action is not self.requested_action:
            raise ValueError("root impact action must equal the requested action")
        if self.signature.purpose != "dependency_impact":
            raise ValueError("dependency-impact signature has the wrong purpose")
        if self.signature.signed_at != self.generated_at:
            raise ValueError("dependency-impact signature time must equal generation time")
        return self


class InvalidationEvent(FrozenModel):
    """Signed declaration that one exact target is no longer eligible for use."""

    governance_type: Literal[GovernanceObjectKind.INVALIDATION_EVENT] = (
        GovernanceObjectKind.INVALIDATION_EVENT
    )
    event_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    action: InvalidationAction
    target: RecallTarget
    dependency_impact_ref: DependencyImpactRef
    reason: NonEmptyStr
    policy_version: SemVer
    effective_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def invalidation_matches_target_and_signature(self) -> InvalidationEvent:
        allowed = _ACTIONS_BY_TARGET_KIND[self.target.target_kind]
        if self.action not in allowed:
            raise ValueError("invalidation action is incompatible with its target kind")
        if self.signature.purpose != "invalidation_event":
            raise ValueError("invalidation signature has the wrong purpose")
        if self.signature.signed_at != self.effective_at:
            raise ValueError("invalidation signature time must equal effective time")
        return self


class TombstoneReceipt(FrozenModel):
    """Signed minimal proof that encrypted payload bytes were deleted."""

    governance_type: Literal[GovernanceObjectKind.TOMBSTONE_RECEIPT] = (
        GovernanceObjectKind.TOMBSTONE_RECEIPT
    )
    receipt_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    payload_digest: Sha256Digest
    byte_length: int = Field(ge=0)
    media_type: NonEmptyStr
    evidence_targets: Annotated[tuple[RecallTarget, ...], Field(min_length=1)]
    invalidation_refs: Annotated[tuple[InvalidationEventRef, ...], Field(min_length=1)]
    deletion_method: Literal["encrypted_payload_unlinked"] = "encrypted_payload_unlinked"
    purged_at: UtcDateTime
    signature: SignatureEnvelope

    @field_validator("evidence_targets")
    @classmethod
    def tombstone_targets_are_sorted_unique(
        cls, value: tuple[RecallTarget, ...]
    ) -> tuple[RecallTarget, ...]:
        keys = tuple(_recall_target_key(item) for item in value)
        if list(keys) != sorted(set(keys)):
            raise ValueError("tombstone Evidence targets must be sorted and unique")
        if any(item.target_kind is not RecallTargetKind.EVIDENCE for item in value):
            raise ValueError("tombstones can reference only Evidence targets")
        return value

    @field_validator("invalidation_refs")
    @classmethod
    def invalidation_refs_are_sorted_unique(
        cls, value: tuple[InvalidationEventRef, ...]
    ) -> tuple[InvalidationEventRef, ...]:
        keys = tuple((item.object_id, item.content_digest) for item in value)
        if list(keys) != sorted(set(keys)):
            raise ValueError("tombstone invalidation references must be sorted and unique")
        return value

    @model_validator(mode="after")
    def tombstone_is_signed(self) -> TombstoneReceipt:
        if self.signature.purpose != "tombstone_receipt":
            raise ValueError("tombstone signature has the wrong purpose")
        if self.signature.signed_at != self.purged_at:
            raise ValueError("tombstone signature time must equal purge time")
        return self


class RecallReport(FrozenModel):
    """Signed completion record for one confirmed dependency impact."""

    governance_type: Literal[GovernanceObjectKind.RECALL_REPORT] = (
        GovernanceObjectKind.RECALL_REPORT
    )
    report_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    dependency_impact_ref: DependencyImpactRef
    invalidation_refs: Annotated[tuple[InvalidationEventRef, ...], Field(min_length=1)]
    tombstone_refs: tuple[TombstoneReceiptRef, ...] = ()
    deactivated_environment_ids: tuple[Identifier, ...] = ()
    purged_payload_digests: tuple[Sha256Digest, ...] = ()
    status: Literal["completed"] = "completed"
    completed_at: UtcDateTime
    policy_version: SemVer
    signature: SignatureEnvelope

    @field_validator(
        "deactivated_environment_ids",
        "purged_payload_digests",
    )
    @classmethod
    def report_values_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("recall report values must be sorted and unique")
        return value

    @field_validator("invalidation_refs", "tombstone_refs")
    @classmethod
    def report_refs_are_sorted_unique(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        keys = tuple((item.object_id, item.content_digest) for item in value)  # type: ignore[attr-defined]
        if list(keys) != sorted(set(keys)):
            raise ValueError("recall report references must be sorted and unique")
        return value

    @model_validator(mode="after")
    def report_is_signed_and_consistent(self) -> RecallReport:
        if bool(self.tombstone_refs) != bool(self.purged_payload_digests):
            raise ValueError("recall report tombstones must match whether payloads were purged")
        if self.signature.purpose != "recall_report":
            raise ValueError("recall-report signature has the wrong purpose")
        if self.signature.signed_at != self.completed_at:
            raise ValueError("recall-report signature time must equal completion time")
        return self


class BlindedTaskDescriptor(FrozenModel):
    """Payload-free held-out task metadata visible to construction components."""

    blind_task_id: BlindTaskId
    blind_family_id: BlindFamilyId
    stratum: TaskStratum


class BlindedSplitManifest(FrozenModel):
    """The complete construction-visible view of the held-out split."""

    manifest_version: Literal["1.0"] = "1.0"
    benchmark_id: Identifier
    held_out_tasks: Annotated[tuple[BlindedTaskDescriptor, ...], Field(min_length=4, max_length=4)]

    @field_validator("held_out_tasks")
    @classmethod
    def tasks_are_sorted_and_blinded(
        cls, value: tuple[BlindedTaskDescriptor, ...]
    ) -> tuple[BlindedTaskDescriptor, ...]:
        keys = tuple(item.blind_task_id for item in value)
        if list(keys) != sorted(set(keys)):
            raise ValueError("blinded held-out tasks must be sorted and unique")
        family_ids = tuple(item.blind_family_id for item in value)
        if len(set(family_ids)) != 4:
            raise ValueError("feasibility pilot requires four distinct blinded task families")
        expected_strata = {
            TaskStratum.DIRECT_TRANSFER,
            TaskStratum.FAILURE_RECURRENCE,
            TaskStratum.COMPOSITIONAL,
            TaskStratum.NEUTRAL_CONTROL,
        }
        if {item.stratum for item in value} != expected_strata:
            raise ValueError("blinded split must contain the four frozen task strata")
        return value


class CustodyManifest(FrozenModel):
    """Signed binding between a blinded split and one external encrypted bundle."""

    governance_type: Literal[GovernanceObjectKind.CUSTODY_MANIFEST] = (
        GovernanceObjectKind.CUSTODY_MANIFEST
    )
    manifest_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    benchmark_id: Identifier
    blinded_split: BlindedSplitManifest
    split_manifest_digest: Sha256Digest
    sealed_bundle_digest: Sha256Digest
    sealed_plaintext_digest: Sha256Digest
    sealed_plaintext_bytes: int = Field(gt=0)
    encryption_algorithm: Literal["AES-256-GCM"] = "AES-256-GCM"
    storage_boundary: Literal["outside_compiler_workspace"] = "outside_compiler_workspace"
    policy_version: SemVer
    sealed_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def custody_binding_is_complete_and_signed(self) -> CustodyManifest:
        if self.blinded_split.benchmark_id != self.benchmark_id:
            raise ValueError("custody manifest benchmark does not match its blinded split")
        if canonical_digest(self.blinded_split) != self.split_manifest_digest:
            raise ValueError("split-manifest digest does not match its blinded manifest")
        if self.signature.purpose != "custody_manifest":
            raise ValueError("custody-manifest signature has the wrong purpose")
        if self.signature.signed_at != self.sealed_at:
            raise ValueError("custody-manifest signature time must equal seal time")
        return self


class ConstructionSplitView(FrozenModel):
    """The only custody metadata made available to construction components."""

    blinded_split: BlindedSplitManifest
    split_manifest_digest: Sha256Digest
    custody_manifest_ref: CustodyManifestRef

    @model_validator(mode="after")
    def view_contains_only_an_exact_blinded_binding(self) -> ConstructionSplitView:
        if canonical_digest(self.blinded_split) != self.split_manifest_digest:
            raise ValueError("construction view split digest does not match blinded metadata")
        return self


class BenchmarkRegistration(FrozenModel):
    """Signed preregistration binding the frozen design to held-out custody."""

    governance_type: Literal[GovernanceObjectKind.BENCHMARK_REGISTRATION] = (
        GovernanceObjectKind.BENCHMARK_REGISTRATION
    )
    registration_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    benchmark_id: Identifier
    design: FeasibilityDesign | InternalFeasibilityDesign
    design_digest: Sha256Digest
    custody_manifest_ref: CustodyManifestRef
    condition_blind_ids: Annotated[tuple[BlindConditionId, ...], Field(min_length=4, max_length=4)]
    construction_cutoff: UtcDateTime
    source_construction_not_before: UtcDateTime
    reveal_not_before: UtcDateTime
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = "sha256_counter_shuffle_v1"
    policy_version: SemVer
    registered_at: UtcDateTime
    signature: SignatureEnvelope

    @field_validator("condition_blind_ids")
    @classmethod
    def condition_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("condition blind IDs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def registration_is_frozen_before_construction(self) -> BenchmarkRegistration:
        if canonical_digest(self.design) != self.design_digest:
            raise ValueError("benchmark design digest does not match the embedded design")
        if self.construction_cutoff > self.registered_at:
            raise ValueError("construction cutoff must be fixed by registration")
        if self.source_construction_not_before < self.registered_at:
            raise ValueError("source construction cannot precede preregistration")
        if self.reveal_not_before <= self.source_construction_not_before:
            raise ValueError("held-out reveal must follow source construction start boundary")
        if self.signature.purpose != "benchmark_registration":
            raise ValueError("benchmark-registration signature has the wrong purpose")
        if self.signature.signed_at != self.registered_at:
            raise ValueError("benchmark-registration signature time must equal registration time")
        return self


class ConditionMaterialReceipt(FrozenModel):
    """Signed frozen material metadata for exactly one benchmark condition."""

    governance_type: Literal[GovernanceObjectKind.CONDITION_MATERIAL_RECEIPT] = (
        GovernanceObjectKind.CONDITION_MATERIAL_RECEIPT
    )
    receipt_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    benchmark_id: Identifier
    registration_ref: BenchmarkRegistrationRef
    condition: BenchmarkCondition
    blind_condition_id: BlindConditionId
    wrapper_digest: Sha256Digest
    material_digest: Sha256Digest
    bundle_digest: Sha256Digest
    eligible_corpus_digest: Sha256Digest | None = None
    source_task_ids: tuple[Identifier, ...] = ()
    source_evaluation_case_ids: tuple[Identifier, ...] = ()
    target_visible_tokens: int = Field(ge=0, le=3000)
    target_visible_utf8_bytes: int = Field(ge=0, le=12000)
    padded: Literal[False] = False
    construction_method: ConditionConstructionMethod
    author_role: ConditionAuthorRole
    author_identity: NonEmptyStr | None = None
    author_context_id: Identifier | None = None
    author_packet_digest: Sha256Digest | None = None
    profile_draft_digest: Sha256Digest | None = None
    reviewer_identity: NonEmptyStr | None = None
    reviewer_context_id: Identifier | None = None
    review_packet_digest: Sha256Digest | None = None
    authoring_minutes: int = Field(ge=0, le=90)
    held_out_accessed: Literal[False] = False
    author_may_score_results: Literal[False] = False
    construction_started_at: UtcDateTime
    frozen_at: UtcDateTime
    policy_version: SemVer
    signature: SignatureEnvelope

    @field_validator("source_task_ids", "source_evaluation_case_ids")
    @classmethod
    def condition_sources_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("condition source IDs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def material_matches_registered_condition_rule(self) -> ConditionMaterialReceipt:
        if self.frozen_at < self.construction_started_at:
            raise ValueError("condition material cannot freeze before construction starts")
        if self.condition is BenchmarkCondition.BASE:
            if self.target_visible_tokens or self.target_visible_utf8_bytes:
                raise ValueError("base condition cannot contain adaptation material")
            if self.source_task_ids or self.source_evaluation_case_ids:
                raise ValueError("base condition cannot use the construction corpus")
            if self.eligible_corpus_digest is not None:
                raise ValueError("base condition cannot bind a source corpus")
            if (
                self.construction_method is not ConditionConstructionMethod.NONE
                or self.author_role is not ConditionAuthorRole.NONE
                or self.author_identity is not None
                or self.author_context_id is not None
                or self.author_packet_digest is not None
                or self.profile_draft_digest is not None
                or self.reviewer_identity is not None
                or self.reviewer_context_id is not None
                or self.review_packet_digest is not None
                or self.authoring_minutes != 0
            ):
                raise ValueError("base condition must use the empty construction rule")
        else:
            if self.target_visible_tokens == 0 or self.target_visible_utf8_bytes == 0:
                raise ValueError("source-derived condition material must be non-empty")
            if self.eligible_corpus_digest is None or not self.source_task_ids:
                raise ValueError("source-derived condition must bind its eligible corpus")
        expected = {
            BenchmarkCondition.ORDINARY_MEMORY: (
                ConditionConstructionMethod.DETERMINISTIC_APPROVED_FEEDBACK,
                ConditionAuthorRole.DETERMINISTIC_RENDERER,
            ),
            BenchmarkCondition.COMPILED_ADAPTATION: (
                ConditionConstructionMethod.COMPILED_RELEASE_PACK,
                ConditionAuthorRole.COMPILER,
            ),
        }
        if self.condition in expected:
            method, role = expected[self.condition]
            if self.construction_method is not method or self.author_role is not role:
                raise ValueError("condition construction method or author role is incorrect")
        if self.condition is BenchmarkCondition.STRONG_STATIC_PROFILE:
            construction_pair = (self.construction_method, self.author_role)
            if construction_pair == (
                ConditionConstructionMethod.INDEPENDENT_HUMAN_PROFILE,
                ConditionAuthorRole.INDEPENDENT_HUMAN,
            ):
                if self.author_identity is None:
                    raise ValueError("legacy strong profile requires an identified human")
                if any(
                    value is not None
                    for value in (
                        self.author_context_id,
                        self.author_packet_digest,
                        self.profile_draft_digest,
                        self.reviewer_identity,
                        self.reviewer_context_id,
                        self.review_packet_digest,
                    )
                ):
                    raise ValueError("legacy human profile cannot claim AI isolation receipts")
            elif construction_pair == (
                ConditionConstructionMethod.ISOLATED_AI_TWO_PASS_PROFILE,
                ConditionAuthorRole.ISOLATED_AI,
            ):
                required_isolation_fields = (
                    self.author_identity,
                    self.author_context_id,
                    self.author_packet_digest,
                    self.profile_draft_digest,
                    self.reviewer_identity,
                    self.reviewer_context_id,
                    self.review_packet_digest,
                )
                if any(value is None for value in required_isolation_fields):
                    raise ValueError(
                        "strong profile requires complete two-pass AI isolation receipts"
                    )
                if (
                    self.author_identity == self.reviewer_identity
                    or self.author_context_id == self.reviewer_context_id
                ):
                    raise ValueError("strong profile AI author and reviewer must be distinct")
            else:
                raise ValueError("strong profile construction method or author role is incorrect")
            if not 1 <= self.authoring_minutes <= 90:
                raise ValueError("strong profile construction must finish within 90 minutes")
        elif self.authoring_minutes != 0:
            raise ValueError("only strong-profile construction records elapsed minutes")
        elif any(
            value is not None
            for value in (
                self.author_context_id,
                self.author_packet_digest,
                self.profile_draft_digest,
                self.reviewer_identity,
                self.reviewer_context_id,
                self.review_packet_digest,
            )
        ):
            raise ValueError("only strong profile may carry AI isolation receipt fields")
        if self.signature.purpose != "condition_material_receipt":
            raise ValueError("condition-material signature has the wrong purpose")
        if self.signature.signed_at != self.frozen_at:
            raise ValueError("condition-material signature time must equal freeze time")
        return self


class TrialResult(FrozenModel):
    """Immutable blinded scoring result; later corrections require adjudication."""

    governance_type: Literal[GovernanceObjectKind.TRIAL_RESULT] = GovernanceObjectKind.TRIAL_RESULT
    result_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    benchmark_id: Identifier
    registration_ref: BenchmarkRegistrationRef
    condition_material_ref: ConditionMaterialReceiptRef
    blind_task_id: BlindTaskId
    blind_condition_id: BlindConditionId
    repetition: int = Field(ge=1, le=2)
    trial_record_digest: Sha256Digest
    environment_digest: Sha256Digest
    task_rubric_digest: Sha256Digest
    automated_test_digest: Sha256Digest
    automated_correctness: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    requirement_coverage: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    change_discipline: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    validity: TrialValidity
    invalid_reason: NonEmptyStr | None = None
    guardrail_codes: tuple[NonEmptyStr, ...] = ()
    scorer_identity: NonEmptyStr
    scored_at: UtcDateTime
    policy_version: SemVer
    signature: SignatureEnvelope

    @field_validator("guardrail_codes")
    @classmethod
    def guardrails_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("trial-result guardrails must be sorted and unique")
        return value

    @model_validator(mode="after")
    def result_is_validated_and_signed(self) -> TrialResult:
        if (self.validity is TrialValidity.INVALID) != (self.invalid_reason is not None):
            raise ValueError("only invalid trials require an invalid reason")
        if self.signature.purpose != "trial_result":
            raise ValueError("trial-result signature has the wrong purpose")
        if self.signature.signed_at != self.scored_at:
            raise ValueError("trial-result signature time must equal scoring time")
        return self

    @property
    def weighted_score(self) -> float | None:
        if self.validity is TrialValidity.INVALID:
            return None
        return (
            0.60 * self.automated_correctness
            + 0.25 * self.requirement_coverage
            + 0.15 * self.change_discipline
        )


class AdjudicatedValue(FrozenModel):
    """Digest-only correction; original and corrected private values stay outside metadata."""

    field_name: AdjudicatedField
    original_value_digest: Sha256Digest
    corrected_value_digest: Sha256Digest

    @model_validator(mode="after")
    def correction_changes_the_derived_value(self) -> AdjudicatedValue:
        if self.original_value_digest == self.corrected_value_digest:
            raise ValueError("adjudicated correction digests must differ")
        return self


class AdjudicationRecord(FrozenModel):
    """Append-only correction linked to an immutable TrialResult."""

    governance_type: Literal[GovernanceObjectKind.ADJUDICATION_RECORD] = (
        GovernanceObjectKind.ADJUDICATION_RECORD
    )
    adjudication_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    benchmark_id: Identifier
    trial_result_ref: TrialResultRef
    sequence: int = Field(gt=0)
    previous_adjudication_ref: AdjudicationRecordRef | None = None
    decision: AdjudicationDecision
    changes: tuple[AdjudicatedValue, ...] = ()
    reason: NonEmptyStr
    reviewer_identity: NonEmptyStr
    adjudicated_at: UtcDateTime
    policy_version: SemVer
    signature: SignatureEnvelope

    @field_validator("changes")
    @classmethod
    def adjudicated_fields_are_unique(
        cls, value: tuple[AdjudicatedValue, ...]
    ) -> tuple[AdjudicatedValue, ...]:
        fields = tuple(item.field_name.value for item in value)
        if list(fields) != sorted(set(fields)):
            raise ValueError("adjudicated fields must be sorted and unique")
        return value

    @model_validator(mode="after")
    def adjudication_extends_history_and_is_signed(self) -> AdjudicationRecord:
        if (self.sequence == 1) != (self.previous_adjudication_ref is None):
            raise ValueError("only the first adjudication omits a previous reference")
        if self.decision is AdjudicationDecision.CORRECT_DERIVED_VALUE and not self.changes:
            raise ValueError("derived-value correction requires digest-only changes")
        if self.decision is not AdjudicationDecision.CORRECT_DERIVED_VALUE and self.changes:
            raise ValueError("only derived-value correction may contain changed fields")
        if self.signature.purpose != "adjudication_record":
            raise ValueError("adjudication signature has the wrong purpose")
        if self.signature.signed_at != self.adjudicated_at:
            raise ValueError("adjudication signature time must equal adjudication time")
        return self


class CustodyAccessEvent(FrozenModel):
    """Signed append-only access decision chained within one custody manifest."""

    governance_type: Literal[GovernanceObjectKind.CUSTODY_ACCESS_EVENT] = (
        GovernanceObjectKind.CUSTODY_ACCESS_EVENT
    )
    event_id: Identifier
    schema_version: GovernanceSchemaVersion = "1.0"
    subject_id: Identifier
    benchmark_id: Identifier
    custody_manifest_ref: CustodyManifestRef
    registration_ref: BenchmarkRegistrationRef | None = None
    sequence: int = Field(gt=0)
    previous_access_event_ref: CustodyAccessEventRef | None = None
    action: CustodyAccessAction
    outcome: CustodyAccessOutcome
    actor_identity: NonEmptyStr
    reason: NonEmptyStr
    occurred_at: UtcDateTime
    policy_version: SemVer
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def access_event_is_chained_and_signed(self) -> CustodyAccessEvent:
        if (self.sequence == 1) != (self.previous_access_event_ref is None):
            raise ValueError("only the first custody access event omits a previous reference")
        if self.action is CustodyAccessAction.SEAL:
            if (
                self.sequence != 1
                or self.outcome is not CustodyAccessOutcome.ALLOWED
                or self.registration_ref is not None
            ):
                raise ValueError("seal must be the first allowed event without a registration")
        elif self.sequence == 1:
            raise ValueError("custody access history must begin with a seal event")
        if self.action is CustodyAccessAction.REQUEST_REVEAL:
            if self.registration_ref is None:
                raise ValueError("reveal request must bind an exact benchmark registration")
        elif self.registration_ref is not None:
            raise ValueError("only reveal requests may bind a benchmark registration")
        if self.signature.purpose != "custody_access_event":
            raise ValueError("custody-access signature has the wrong purpose")
        if self.signature.signed_at != self.occurred_at:
            raise ValueError("custody-access signature time must equal occurrence time")
        return self


def _recall_target_key(value: RecallTarget) -> tuple[str, str, str, str]:
    return (
        value.target_kind.value,
        value.object_id,
        value.record_version or "",
        value.content_digest,
    )


_ACTIONS_BY_TARGET_KIND: dict[RecallTargetKind, frozenset[InvalidationAction]] = {
    RecallTargetKind.CONSENT_RECEIPT: frozenset({InvalidationAction.REVOKE_CONSENT}),
    RecallTargetKind.CAPTURE_RECEIPT: frozenset({InvalidationAction.EXCLUDE_DEPENDENCY}),
    RecallTargetKind.TASK_RECORD: frozenset({InvalidationAction.EXCLUDE_DEPENDENCY}),
    RecallTargetKind.OUTCOME: frozenset({InvalidationAction.EXCLUDE_DEPENDENCY}),
    RecallTargetKind.EVIDENCE: frozenset(
        {
            InvalidationAction.RESTRICT_EVIDENCE,
            InvalidationAction.PURGE_EVIDENCE,
            InvalidationAction.EXCLUDE_DEPENDENCY,
        }
    ),
    RecallTargetKind.EVALUATION_CASE: frozenset({InvalidationAction.EXCLUDE_DEPENDENCY}),
    RecallTargetKind.LESSON_CANDIDATE: frozenset({InvalidationAction.EXCLUDE_DEPENDENCY}),
    RecallTargetKind.ARTIFACT: frozenset(
        {InvalidationAction.REVOKE_ARTIFACT, InvalidationAction.EXCLUDE_DEPENDENCY}
    ),
    RecallTargetKind.RELEASE: frozenset({InvalidationAction.RETIRE_RELEASE}),
    RecallTargetKind.TARGET_PACK: frozenset({InvalidationAction.INVALIDATE_TARGET_PACK}),
    RecallTargetKind.ACTIVATION: frozenset({InvalidationAction.DEACTIVATE_ACTIVATION}),
}


type SignedRecallObject = DependencyImpact | InvalidationEvent | TombstoneReceipt | RecallReport
type SignedBenchmarkObject = (
    CustodyManifest
    | BenchmarkRegistration
    | ConditionMaterialReceipt
    | TrialResult
    | AdjudicationRecord
    | CustodyAccessEvent
)
type SignedGovernanceObject = (
    SignerIdentity
    | ConsentReceipt
    | CaptureReceipt
    | GovernanceEvent
    | SignedRecallObject
    | SignedBenchmarkObject
)
