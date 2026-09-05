from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.copilot_delivery import (
    CopilotConnectionError,
    CopilotConnectionService,
    CopilotHookFileService,
)
from adaptation_compiler_lab.domain import PermittedUse
from adaptation_compiler_lab.governance import SignerIdentity, SignerRole
from adaptation_compiler_lab.governance.signing import GovernanceSigner, create_signer_identity
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64


def _parts(
    tmp_path: Path,
) -> tuple[CopilotConnectionService, GovernanceSigner, SignerIdentity, Path, Path]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-owner-key",
        subject_id="temper-owner",
    )
    identity = create_signer_identity(
        signer,
        roles=tuple(sorted(SignerRole, key=lambda item: item.value)),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=31),
    )
    raw_store = LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"d" * 32))
    hook_files = CopilotHookFileService(
        raw_store=raw_store,
        signer=signer,
        now=lambda: NOW,
        state_root=tmp_path / "state",
    )
    hook_path = tmp_path / ".copilot" / "hooks" / "temper.json"
    helper_path = tmp_path / "Temper" / "temper-hook.exe"
    helper_path.parent.mkdir()
    helper_path.write_bytes(b"signed helper")
    service = CopilotConnectionService(
        subject_id="temper-owner",
        projects={"green-meadow": DIGEST_A},
        hook_files=hook_files,
        hook_path=hook_path,
        helper_path=helper_path,
        signer=signer,
        signer_identity=identity,
        state_root=tmp_path / "state",
        now=lambda: NOW,
    )
    return service, signer, identity, hook_path, helper_path


def test_connection_is_delivery_only_consent_bound_and_restart_safe(tmp_path: Path) -> None:
    service, signer, identity, hook_path, helper_path = _parts(tmp_path)
    preview = service.preview(operation="connect")
    assert preview.learning_enabled is False
    assert preview.delivery_enabled is True
    with pytest.raises(CopilotConnectionError, match="consent"):
        service.apply(
            preview_token=preview.hook_file.preview_token,
            expected_before_digest=preview.hook_file.before_digest,
            consent_confirmed=False,
            idempotency_key="connect",
        )
    receipt = service.apply(
        preview_token=preview.hook_file.preview_token,
        expected_before_digest=preview.hook_file.before_digest,
        consent_confirmed=True,
        idempotency_key="connect",
    )
    assert receipt.learning_enabled is False
    assert set(receipt.consent.permitted_uses) == {
        PermittedUse.AUDIT,
        PermittedUse.TARGET_DELIVERY,
    }
    assert receipt.consent.scope.target_families == ("copilot-cli",)
    assert service.status().state == "connected"
    assert service.authorization("green-meadow", effective_at=NOW) is not None
    assert service.authorization("outside", effective_at=NOW) is None

    restarted = CopilotConnectionService(
        subject_id="temper-owner",
        projects={"green-meadow": DIGEST_A},
        hook_files=CopilotHookFileService(
            raw_store=LocalRawPayloadStore(
                tmp_path / "raw", encryption_key=RawEncryptionKey(b"d" * 32)
            ),
            signer=signer,
            now=lambda: NOW,
            state_root=tmp_path / "state",
        ),
        hook_path=hook_path,
        helper_path=helper_path,
        signer=signer,
        signer_identity=identity,
        state_root=tmp_path / "state",
        now=lambda: NOW,
    )
    assert restarted.status().state == "connected"
    assert (
        restarted.apply(
            preview_token=preview.hook_file.preview_token,
            expected_before_digest=preview.hook_file.before_digest,
            consent_confirmed=True,
            idempotency_key="connect",
        )
        == receipt
    )


def test_disconnect_removes_owned_file_and_drift_pauses_delivery(tmp_path: Path) -> None:
    service, _signer, _identity, hook_path, helper_path = _parts(tmp_path)
    connect = service.preview(operation="connect")
    service.apply(
        preview_token=connect.hook_file.preview_token,
        expected_before_digest=connect.hook_file.before_digest,
        consent_confirmed=True,
        idempotency_key="connect",
    )
    helper_path.write_bytes(b"changed helper")
    assert service.status().state == "attention"
    assert service.authorization("green-meadow", effective_at=NOW) is None

    helper_path.write_bytes(b"signed helper")
    disconnect = service.preview(operation="disconnect")
    service.apply(
        preview_token=disconnect.hook_file.preview_token,
        expected_before_digest=disconnect.hook_file.before_digest,
        consent_confirmed=True,
        idempotency_key="disconnect",
    )
    assert service.status().state == "available"
    assert not hook_path.exists()
