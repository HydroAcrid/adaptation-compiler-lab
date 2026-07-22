"""Signed governance, v1.1 Evidence admission, and tamper tests."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from adaptation_compiler_lab.application.governance import (
    EvidenceGovernanceError,
    validate_evidence_governance,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    AuthorityClass,
    ClaimType,
    Evidence,
    EvidenceState,
    Partition,
    PayloadReference,
    PermittedUse,
    PrivacyContext,
    RedactionState,
    Scope,
    SensitivityClass,
    SourceClass,
    TaskRecordRef,
)
from adaptation_compiler_lab.governance import (
    CaptureReceipt,
    ConsentReceipt,
    GovernanceEventType,
    SignerIdentity,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    SignatureVerificationError,
    create_signer_identity,
    governance_ref,
    sign_capture,
    sign_consent,
    sign_governance_event,
    verify_signed_governance,
    write_new_private_key,
)

NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
ROLES = (
    SignerRole.ACTIVATION,
    SignerRole.CONSENT,
    SignerRole.CUSTODY,
    SignerRole.RELEASE,
    SignerRole.REVIEW,
)


def _identity() -> tuple[GovernanceSigner, SignerIdentity]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="kevin-governance-1",
        subject_id="kevin",
    )
    identity = create_signer_identity(
        signer,
        roles=ROLES,
        created_at=NOW,
        expires_at=NOW + timedelta(days=365),
    )
    return signer, identity


def _consent(signer: GovernanceSigner) -> ConsentReceipt:
    return sign_consent(
        {
            "receipt_id": "consent-1",
            "subject_id": "kevin",
            "source_selector": {
                "source_system": "codex_app_server",
                "selection_method": "explicit_task_ids",
                "source_ids": ["task-1"],
            },
            "scope": {"subject_ids": ["kevin"]},
            "permitted_uses": ["construction"],
            "issued_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=7)).isoformat(),
            "retention_until": (NOW + timedelta(days=30)).isoformat(),
            "policy_version": "1.0.0",
        },
        signer,
    )


def _capture(signer: GovernanceSigner, consent: ConsentReceipt) -> CaptureReceipt:
    return sign_capture(
        {
            "receipt_id": "capture-1",
            "subject_id": "kevin",
            "consent_ref": governance_ref(consent).model_dump(mode="json"),
            "source_selector": consent.source_selector.model_dump(mode="json"),
            "source_version": "codex-app-server-test",
            "source_schema_digest": DIGEST,
            "payload_digest": DIGEST,
            "captured_at": (NOW + timedelta(minutes=1)).isoformat(),
            "synthetic": False,
        },
        signer,
    )


def _evidence(consent: ConsentReceipt, capture: CaptureReceipt) -> Evidence:
    actor = ActorRef(actor_id="kevin", kind=ActorKind.USER)
    return Evidence(
        record_id="evidence-1",
        schema_version="1.1",
        record_version="1.0.0",
        created_at=NOW + timedelta(minutes=2),
        created_by=actor,
        policy_version="1.0.0",
        observed_at=NOW,
        producer=actor,
        source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
        authority_class=AuthorityClass.USER_NORMATIVE,
        authority_reason="Explicit user-authored correction.",
        allowed_claim_types=(ClaimType.USER_CORRECTION,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator="sha256/aa/" + "a" * 64,
            content_digest=DIGEST,
            media_type="application/json",
            byte_length=12,
        ),
        task_ref=TaskRecordRef(record_id="task-1", record_version="1.0.0"),
        consent_receipt_ref=governance_ref(consent),
        capture_receipt_ref=governance_ref(capture),
        scope=Scope(subject_ids=("kevin",)),
        privacy=PrivacyContext(
            sensitivity=SensitivityClass.PRIVATE,
            consent_basis="signed-consent-receipt",
            permitted_uses=(PermittedUse.CONSTRUCTION,),
        ),
        partition=Partition.CONSTRUCTION,
    )


def test_identity_consent_capture_and_evidence_lineage_verify() -> None:
    signer, identity = _identity()
    consent = _consent(signer)
    capture = _capture(signer, consent)
    evidence = _evidence(consent, capture)

    verify_signed_governance(identity, identity)
    verify_signed_governance(consent, identity)
    verify_signed_governance(capture, identity)
    validate_evidence_governance(
        evidence,
        consent=consent,
        capture=capture,
        identity=identity,
    )


def test_tampering_or_wrong_key_fails_signature_verification() -> None:
    signer, identity = _identity()
    consent = _consent(signer)
    tampered = consent.model_copy(update={"policy_version": "9.9.9"})

    with pytest.raises(SignatureVerificationError, match="verification failed"):
        verify_signed_governance(tampered, identity)

    _, wrong_identity = _identity()
    wrong_identity = wrong_identity.model_copy(update={"identity_id": "other-identity"})
    with pytest.raises(SignatureVerificationError):
        verify_signed_governance(consent, wrong_identity)


def test_identity_rejects_a_fingerprint_not_derived_from_its_public_key() -> None:
    _, identity = _identity()
    payload = identity.model_dump(mode="python")
    payload["key_fingerprint"] = "sha256:" + "0" * 64
    payload["signature"] = identity.signature.model_copy(
        update={"key_fingerprint": "sha256:" + "0" * 64}
    )

    with pytest.raises(ValidationError, match="fingerprint does not match"):
        SignerIdentity.model_validate(payload)


@given(index=st.integers(min_value=0, max_value=63), bit=st.integers(min_value=0, max_value=7))
def test_any_single_signature_bit_tamper_fails(index: int, bit: int) -> None:
    signer, identity = _identity()
    consent = _consent(signer)
    signature = bytearray(base64.b64decode(consent.signature.signature_base64))
    signature[index] ^= 1 << bit
    envelope = consent.signature.model_copy(
        update={"signature_base64": base64.b64encode(signature).decode("ascii")}
    )
    tampered = consent.model_copy(update={"signature": envelope})

    with pytest.raises(SignatureVerificationError):
        verify_signed_governance(tampered, identity)


@given(other_subject=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12))
def test_cross_subject_signed_receipts_never_verify(other_subject: str) -> None:
    if other_subject == "kevin":
        return
    signer, identity = _identity()
    receipt = sign_consent(
        {
            "receipt_id": "cross-subject-consent",
            "subject_id": other_subject,
            "source_selector": {
                "source_system": "synthetic_fixture",
                "selection_method": "synthetic_fixture",
                "source_ids": ["fixture-1"],
            },
            "scope": {"subject_ids": [other_subject]},
            "permitted_uses": ["construction"],
            "issued_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=1)).isoformat(),
            "retention_until": (NOW + timedelta(days=30)).isoformat(),
            "policy_version": "1.0.0",
        },
        signer,
    )

    with pytest.raises(SignatureVerificationError, match="subject boundary"):
        verify_signed_governance(receipt, identity)


def test_signing_key_cannot_be_created_inside_a_git_repository(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)

    with pytest.raises(ValueError, match="Git repository"):
        write_new_private_key(
            repository / "identity.pem",
            passphrase="synthetic-test-passphrase",
            workspace_root=workspace,
        )


@pytest.mark.parametrize(
    ("event_type", "purpose"),
    [
        (GovernanceEventType.REVIEW_DECISION, "review"),
        (GovernanceEventType.RELEASE_DECISION, "release"),
        (GovernanceEventType.ACTIVATION_DECISION, "activation"),
        (GovernanceEventType.CUSTODY_ACTION, "custody"),
    ],
)
def test_review_release_activation_and_custody_events_are_signed(
    event_type: GovernanceEventType, purpose: str
) -> None:
    signer, identity = _identity()
    event = sign_governance_event(
        {
            "event_id": f"event-{purpose}",
            "subject_id": "kevin",
            "event_type": event_type.value,
            "target_ref": "synthetic:target@1.0.0",
            "target_digest": DIGEST,
            "decision": "approved",
            "reason": "Synthetic governance contract test.",
            "policy_version": "1.0.0",
            "occurred_at": NOW.isoformat(),
        },
        signer,
    )

    assert event.signature.purpose == purpose
    verify_signed_governance(event, identity)


def test_non_synthetic_evidence_v11_requires_both_exact_receipt_refs() -> None:
    signer, _ = _identity()
    consent = _consent(signer)
    capture = _capture(signer, consent)
    payload = _evidence(consent, capture).model_dump(mode="python")
    payload["capture_receipt_ref"] = None

    with pytest.raises(ValidationError, match="requires exact consent and capture"):
        Evidence.model_validate(payload)


def test_evidence_governance_rejects_scope_or_digest_substitution() -> None:
    signer, identity = _identity()
    consent = _consent(signer)
    capture = _capture(signer, consent)
    evidence = _evidence(consent, capture)
    other_digest = "sha256:" + hashlib.sha256(b"other").hexdigest()
    unsigned = capture.model_dump(mode="json", round_trip=True, exclude={"signature"})
    unsigned["payload_digest"] = other_digest
    substituted = sign_capture(unsigned, signer)

    with pytest.raises(EvidenceGovernanceError, match="reference does not match"):
        validate_evidence_governance(
            evidence,
            consent=consent,
            capture=substituted,
            identity=identity,
        )


def test_evidence_governance_rejects_capture_after_consent_expiry() -> None:
    signer, identity = _identity()
    consent = _consent(signer)
    unsigned = _capture(signer, consent).model_dump(
        mode="json", round_trip=True, exclude={"signature"}
    )
    unsigned["captured_at"] = (consent.expires_at + timedelta(seconds=1)).isoformat()
    late_capture = sign_capture(unsigned, signer)
    evidence = _evidence(consent, late_capture)

    with pytest.raises(EvidenceGovernanceError, match="validity window"):
        validate_evidence_governance(
            evidence,
            consent=consent,
            capture=late_capture,
            identity=identity,
        )
