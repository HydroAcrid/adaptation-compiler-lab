"""Append-only signed governance persistence tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.governance import (
    GovernanceObjectKind,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    sign_consent,
)
from adaptation_compiler_lab.persistence.errors import IntegrityError, RecordConflictError
from adaptation_compiler_lab.persistence.governance import GovernanceLedger

NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)


def _ledger(path: Path, subject: str = "kevin") -> GovernanceLedger:
    ledger = GovernanceLedger(path, subject_id=subject)
    assert ledger.initialize() == 7
    return ledger


def test_signed_objects_round_trip_and_are_idempotent(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "ledger.sqlite3")
    signer = GovernanceSigner(Ed25519PrivateKey.generate(), "signer-1", "kevin")
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CONSENT,),
        created_at=NOW,
    )
    consent = sign_consent(
        {
            "receipt_id": "consent-1",
            "subject_id": "kevin",
            "source_selector": {
                "source_system": "synthetic_fixture",
                "selection_method": "synthetic_fixture",
                "source_ids": ["fixture-1"],
            },
            "scope": {"subject_ids": ["kevin"]},
            "permitted_uses": ["construction"],
            "issued_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=1)).isoformat(),
            "retention_until": (NOW + timedelta(days=30)).isoformat(),
            "policy_version": "1.0.0",
        },
        signer,
    )

    assert ledger.add(identity)
    assert ledger.add(consent)
    assert not ledger.add(consent)
    assert ledger.get(GovernanceObjectKind.CONSENT_RECEIPT, "consent-1") == consent


def test_cross_subject_and_immutable_identity_conflicts_fail(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = _ledger(path)
    signer = GovernanceSigner(Ed25519PrivateKey.generate(), "signer-1", "kevin")
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CONSENT,),
        created_at=NOW,
    )
    ledger.add(identity)

    with pytest.raises(IntegrityError, match="subject"):
        _ledger(path, "other").add(identity)

    conflicting_signer = GovernanceSigner(Ed25519PrivateKey.generate(), "signer-1", "kevin")
    conflicting = create_signer_identity(
        conflicting_signer,
        roles=(SignerRole.CONSENT,),
        created_at=NOW,
    )
    with pytest.raises(RecordConflictError):
        ledger.add(conflicting)
