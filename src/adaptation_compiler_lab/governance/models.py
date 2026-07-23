"""Signed governance contracts for identity, consent, capture, and audited actions."""

from __future__ import annotations

import base64
import hashlib
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

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
    ConsentReceiptRef,
    DependencyImpactRef,
    InvalidationEventRef,
    TombstoneReceiptRef,
)
from adaptation_compiler_lab.domain.values import Scope, strings_are_sorted_unique

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

    source_system: Literal["synthetic_fixture", "codex_app_server"]
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
type SignedGovernanceObject = (
    SignerIdentity | ConsentReceipt | CaptureReceipt | GovernanceEvent | SignedRecallObject
)
