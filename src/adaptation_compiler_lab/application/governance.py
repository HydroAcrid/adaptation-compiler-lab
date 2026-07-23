"""Fail-closed admission policy tying Evidence v1.1 to signed governance."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from adaptation_compiler_lab.domain import Evidence, PermittedUse, SourceClass, scope_is_within
from adaptation_compiler_lab.governance import (
    CaptureReceipt,
    ConsentReceipt,
    InvalidationAction,
    InvalidationEvent,
    RecallTargetKind,
    SignerIdentity,
)
from adaptation_compiler_lab.governance.signing import governance_ref, verify_signed_governance


class EvidenceGovernanceError(ValueError):
    """Raised when evidence is not covered by exact active signed authorization."""


def validate_evidence_governance(
    evidence: Evidence,
    *,
    consent: ConsentReceipt | None,
    capture: CaptureReceipt | None,
    identity: SignerIdentity | None,
    invalidation_events: Iterable[InvalidationEvent] = (),
    effective_at: datetime | None = None,
) -> None:
    """Validate exact references, signatures, source, scope, use, expiry, and retention."""

    if evidence.schema_version == "1.0":
        if evidence.source_class is not SourceClass.SYNTHETIC:
            raise EvidenceGovernanceError(
                "non-synthetic Evidence v1.0 is readable but not eligible for new admission"
            )
        return
    if evidence.source_class is SourceClass.SYNTHETIC:
        if any(value is not None for value in (consent, capture, identity)):
            raise EvidenceGovernanceError("synthetic Evidence must not borrow real governance")
        return
    if consent is None or capture is None or identity is None:
        raise EvidenceGovernanceError(
            "non-synthetic Evidence requires consent, capture, and signer"
        )
    verify_signed_governance(identity, identity)
    verify_signed_governance(consent, identity)
    verify_signed_governance(capture, identity)
    if evidence.consent_receipt_ref != governance_ref(consent):
        raise EvidenceGovernanceError("Evidence consent reference does not match signed content")
    if evidence.capture_receipt_ref != governance_ref(capture):
        raise EvidenceGovernanceError("Evidence capture reference does not match signed content")
    if capture.consent_ref != governance_ref(consent):
        raise EvidenceGovernanceError("capture does not bind the exact consent receipt")
    for event in invalidation_events:
        verify_signed_governance(event, identity)
        if (
            event.action is InvalidationAction.REVOKE_CONSENT
            and event.target.target_kind is RecallTargetKind.CONSENT_RECEIPT
            and event.target.object_id == consent.receipt_id
            and event.target.content_digest == governance_ref(consent).content_digest
        ):
            raise EvidenceGovernanceError("Evidence consent has been revoked")
    if effective_at is not None:
        if effective_at.tzinfo is None or effective_at.utcoffset() is None:
            raise EvidenceGovernanceError("governance evaluation time must be timezone-aware")
        if effective_at >= consent.expires_at:
            raise EvidenceGovernanceError("expired consent cannot admit Evidence")
    if evidence.scope.subject_ids != (consent.subject_id,):
        raise EvidenceGovernanceError("Evidence subject does not match consent subject")
    if not scope_is_within(evidence.scope, consent.scope):
        raise EvidenceGovernanceError("Evidence scope exceeds consent scope")
    if not set(evidence.privacy.permitted_uses).issubset(consent.permitted_uses):
        raise EvidenceGovernanceError("Evidence permitted uses exceed consent")
    if evidence.observed_at > consent.expires_at:
        raise EvidenceGovernanceError("Evidence observation occurred after consent expiry")
    if capture.captured_at < consent.issued_at or capture.captured_at > consent.expires_at:
        raise EvidenceGovernanceError("capture occurred outside the consent validity window")
    if capture.captured_at > consent.retention_until:
        raise EvidenceGovernanceError("capture occurred after the retention deadline")
    if evidence.payload is None or evidence.payload.content_digest != capture.payload_digest:
        raise EvidenceGovernanceError("capture payload digest does not match Evidence")
    if capture.source_selector != consent.source_selector:
        raise EvidenceGovernanceError("capture source selector differs from consent")
    required_use = {
        "construction": PermittedUse.CONSTRUCTION,
        "development": PermittedUse.DEVELOPMENT_EVALUATION,
        "held_out": PermittedUse.BENCHMARK,
    }.get(evidence.partition.value)
    if required_use is not None and required_use not in consent.permitted_uses:
        raise EvidenceGovernanceError("consent does not permit the Evidence partition")
