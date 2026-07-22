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
)
from adaptation_compiler_lab.domain.values import Scope, strings_are_sorted_unique

GovernanceSchemaVersion = Literal["1.0"]
CanonicalizationVersion = Literal["1.0.0"]


class GovernanceObjectKind(StrEnum):
    SIGNER_IDENTITY = "signer_identity"
    CONSENT_RECEIPT = "consent_receipt"
    CAPTURE_RECEIPT = "capture_receipt"
    GOVERNANCE_EVENT = "governance_event"


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


type SignedGovernanceObject = SignerIdentity | ConsentReceipt | CaptureReceipt | GovernanceEvent
