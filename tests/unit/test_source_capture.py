"""Consent-first encrypted source-capture tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.application.source_capture import (
    PILOT_PERMITTED_USES,
    SourceCaptureError,
    SourceCaptureRequest,
    SourceCaptureService,
)
from adaptation_compiler_lab.connectors.models import (
    SourceTaskPage,
    SourceTaskSnapshot,
    SourceTaskSummary,
    SourceTurnDescriptor,
    TerminalTurnStatus,
)
from adaptation_compiler_lab.governance import (
    CaptureReceipt,
    GovernanceObjectKind,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    sign_consent,
)
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.serialization import canonical_digest

NOW = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
SCHEMA_DIGEST = "sha256:" + "b" * 64
PAYLOAD = b'{"id":"task-1","turns":[]}'


class FakeSourceConnector:
    def __init__(self, *, updated_at: datetime = NOW - timedelta(hours=1)) -> None:
        self.read_ids: list[str] = []
        self.updated_at = updated_at

    @property
    def source_version(self) -> str:
        return "0.145.0-alpha.30"

    @property
    def source_schema_digest(self) -> str:
        return SCHEMA_DIGEST

    def list_completed_tasks(
        self,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> SourceTaskPage:
        return SourceTaskPage(
            tasks=(
                SourceTaskSummary(
                    task_id="task-1",
                    created_at_epoch_seconds=int((NOW - timedelta(days=1)).timestamp()),
                    updated_at_epoch_seconds=int(self.updated_at.timestamp()),
                    cli_version=self.source_version,
                    status="notLoaded",
                    source_digest=SCHEMA_DIGEST,
                    cwd_digest=SCHEMA_DIGEST,
                ),
            )
        )

    def read_completed_task(self, task_id: str) -> SourceTaskSnapshot:
        self.read_ids.append(task_id)
        from adaptation_compiler_lab.connectors.pins import sha256_bytes

        return SourceTaskSnapshot(
            task_id=task_id,
            source_version=self.source_version,
            source_schema_digest=self.source_schema_digest,
            raw_payload=PAYLOAD,
            payload_digest=sha256_bytes(PAYLOAD),
            turns=(
                SourceTurnDescriptor(
                    turn_id="turn-1",
                    status=TerminalTurnStatus.COMPLETED,
                    item_count=2,
                ),
            ),
        )


def _service(
    tmp_path: Path,
    *,
    expires_at: datetime | None = None,
) -> tuple[SourceCaptureService, FakeSourceConnector, GovernanceLedger, LocalRawPayloadStore]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="kevin-source-identity",
        subject_id="kevin",
    )
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CONSENT,),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=90),
    )
    ledger = GovernanceLedger(tmp_path / "ledger.sqlite3", subject_id="kevin")
    ledger.initialize()
    ledger.add(identity)
    consent = sign_consent(
        {
            "receipt_id": "consent-task-1",
            "subject_id": "kevin",
            "source_selector": {
                "source_system": "codex_app_server",
                "selection_method": "explicit_task_ids",
                "source_ids": ["task-1"],
            },
            "scope": {"subject_ids": ["kevin"]},
            "permitted_uses": [item.value for item in PILOT_PERMITTED_USES],
            "issued_at": (NOW - timedelta(hours=1)).isoformat(),
            "expires_at": (expires_at or NOW + timedelta(days=7)).isoformat(),
            "retention_until": (NOW + timedelta(days=30)).isoformat(),
            "policy_version": "1.0.0",
        },
        signer,
    )
    ledger.add(consent)
    raw_store = LocalRawPayloadStore(
        tmp_path / "raw",
        encryption_key=RawEncryptionKey(b"\x11" * 32),
    )
    connector = FakeSourceConnector()
    service = SourceCaptureService(
        connector=connector,
        raw_store=raw_store,
        governance_ledger=ledger,
        signer=signer,
        identity=identity,
        subject_id="kevin",
    )
    return service, connector, ledger, raw_store


def _request(*, task_id: str = "task-1") -> SourceCaptureRequest:
    return SourceCaptureRequest(
        task_id=task_id,
        consent_receipt_id="consent-task-1",
        capture_receipt_id="capture-task-1",
        captured_at=NOW,
    )


def test_exact_consent_captures_encrypted_payload_and_signed_receipt(tmp_path: Path) -> None:
    service, connector, ledger, raw_store = _service(tmp_path)

    result = service.capture(_request())

    assert connector.read_ids == ["task-1"]
    assert result.payload_size_bytes == len(PAYLOAD)
    assert (
        raw_store.read(
            raw_store.reference_for(
                PAYLOAD,
                media_type="application/vnd.openai.codex-thread+json",
            )
        )
        == PAYLOAD
    )
    stored = ledger.get(GovernanceObjectKind.CAPTURE_RECEIPT, "capture-task-1")
    assert isinstance(stored, CaptureReceipt)
    assert canonical_digest(stored) == canonical_digest(result.capture_receipt)
    encrypted = (raw_store.root / result.encrypted_locator).read_bytes()
    assert PAYLOAD not in encrypted


def test_wrong_task_or_expired_consent_fails_before_source_read(tmp_path: Path) -> None:
    service, connector, _, _ = _service(tmp_path)

    with pytest.raises(SourceCaptureError, match="exactly"):
        service.capture(_request(task_id="task-2"))
    assert connector.read_ids == []

    expired_service, expired_connector, _, _ = _service(
        tmp_path / "expired",
        expires_at=NOW,
    )
    with pytest.raises(SourceCaptureError, match="validity"):
        expired_service.capture(_request())
    assert expired_connector.read_ids == []


def test_duplicate_receipt_fails_before_second_source_read(tmp_path: Path) -> None:
    service, connector, _, _ = _service(tmp_path)
    service.capture(_request())

    with pytest.raises(SourceCaptureError, match="already in use"):
        service.capture(_request())
    assert connector.read_ids == ["task-1"]


def test_recently_changing_source_fails_before_thread_read(tmp_path: Path) -> None:
    service, connector, _, _ = _service(tmp_path)
    connector.updated_at = NOW - timedelta(minutes=14)

    with pytest.raises(SourceCaptureError, match="quiescence"):
        service.capture(_request())
    assert connector.read_ids == []
