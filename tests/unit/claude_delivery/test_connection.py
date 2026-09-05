from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.claude_delivery import (
    ClaudeConnectionError,
    ClaudeConnectionService,
    ClaudeHookSettingsService,
)
from adaptation_compiler_lab.governance import SignerIdentity, SignerRole
from adaptation_compiler_lab.governance.signing import GovernanceSigner, create_signer_identity
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _parts(
    tmp_path: Path,
    *,
    projects: dict[str, str] | None = None,
) -> tuple[ClaudeConnectionService, GovernanceSigner, SignerIdentity, Path, Path]:
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
    raw_store = LocalRawPayloadStore(
        tmp_path / "raw",
        encryption_key=RawEncryptionKey(b"c" * 32),
    )
    state_root = tmp_path / "state"
    settings = ClaudeHookSettingsService(
        raw_store=raw_store,
        signer=signer,
        now=lambda: NOW,
        state_root=state_root,
    )
    settings_path = tmp_path / ".claude" / "settings.json"
    helper_path = tmp_path / "Temper" / "temper-hook.exe"
    helper_path.parent.mkdir()
    helper_path.write_bytes(b"signed synthetic helper")
    service = ClaudeConnectionService(
        subject_id="temper-owner",
        projects=projects or {"green-meadow": DIGEST_A, "kairn": DIGEST_B},
        settings=settings,
        settings_path=settings_path,
        helper_path=helper_path,
        signer=signer,
        signer_identity=identity,
        state_root=state_root,
        now=lambda: NOW,
    )
    return service, signer, identity, settings_path, helper_path


def test_connection_requires_previewed_consent_and_is_restart_safe(tmp_path: Path) -> None:
    service, signer, identity, settings_path, helper_path = _parts(tmp_path)
    preview = service.preview(operation="connect")

    with pytest.raises(ClaudeConnectionError, match="consent"):
        service.apply(
            preview_token=preview.settings.preview_token,
            expected_before_digest=preview.settings.before_digest,
            consent_confirmed=False,
            idempotency_key="connect-one",
        )

    connected = service.apply(
        preview_token=preview.settings.preview_token,
        expected_before_digest=preview.settings.before_digest,
        consent_confirmed=True,
        idempotency_key="connect-one",
    )
    assert connected.operation == "connect"
    assert connected.consent.source_selector.source_system == "claude_code_hook"
    assert connected.consent.source_selector.source_ids == ("green-meadow", "kairn")
    assert service.status().state == "connected"
    assert service.authorization("green-meadow") is not None
    assert service.authorization("outside") is None
    assert "temper-hook" in settings_path.read_text(encoding="utf-8")

    restarted_settings = ClaudeHookSettingsService(
        raw_store=LocalRawPayloadStore(
            tmp_path / "raw", encryption_key=RawEncryptionKey(b"c" * 32)
        ),
        signer=signer,
        now=lambda: NOW,
        state_root=tmp_path / "state",
    )
    restarted = ClaudeConnectionService(
        subject_id="temper-owner",
        projects={"green-meadow": DIGEST_A, "kairn": DIGEST_B},
        settings=restarted_settings,
        settings_path=settings_path,
        helper_path=helper_path,
        signer=signer,
        signer_identity=identity,
        state_root=tmp_path / "state",
        now=lambda: NOW,
    )
    assert restarted.status().state == "connected"
    assert (
        restarted.apply(
            preview_token=preview.settings.preview_token,
            expected_before_digest=preview.settings.before_digest,
            consent_confirmed=True,
            idempotency_key="connect-one",
        )
        == connected
    )


def test_disconnect_removes_only_temper_hooks_and_disables_authority(tmp_path: Path) -> None:
    service, _signer, _identity, settings_path, _helper_path = _parts(tmp_path)
    settings_path.parent.mkdir()
    settings_path.write_text('{"theme":"dark"}\n', encoding="utf-8")
    connect = service.preview(operation="connect")
    service.apply(
        preview_token=connect.settings.preview_token,
        expected_before_digest=connect.settings.before_digest,
        consent_confirmed=True,
        idempotency_key="connect",
    )
    disconnect = service.preview(operation="disconnect")
    receipt = service.apply(
        preview_token=disconnect.settings.preview_token,
        expected_before_digest=disconnect.settings.before_digest,
        consent_confirmed=True,
        idempotency_key="disconnect",
    )

    assert receipt.operation == "disconnect"
    assert service.status().state == "available"
    assert service.authorization("green-meadow") is None
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {"theme": "dark"}


def test_helper_or_project_drift_requires_attention(tmp_path: Path) -> None:
    service, signer, identity, settings_path, helper_path = _parts(tmp_path)
    preview = service.preview(operation="connect")
    service.apply(
        preview_token=preview.settings.preview_token,
        expected_before_digest=preview.settings.before_digest,
        consent_confirmed=True,
        idempotency_key="connect",
    )
    helper_path.write_bytes(b"changed")
    assert service.status().state == "attention"
    assert service.authorization("green-meadow") is None

    with pytest.raises(ClaudeConnectionError, match="failed verification"):
        index_path = tmp_path / "state" / "claude-delivery" / "connection-receipts.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["entries"][0]["receipt"]["delivery_enabled"] = False
        index_path.write_text(json.dumps(index), encoding="utf-8")
        settings_service = ClaudeHookSettingsService(
            raw_store=LocalRawPayloadStore(
                tmp_path / "raw", encryption_key=RawEncryptionKey(b"c" * 32)
            ),
            signer=signer,
            now=lambda: NOW,
            state_root=tmp_path / "state",
        )
        ClaudeConnectionService(
            subject_id="temper-owner",
            projects={"green-meadow": DIGEST_A, "kairn": DIGEST_B},
            settings=settings_service,
            settings_path=settings_path,
            helper_path=helper_path,
            signer=signer,
            signer_identity=identity,
            state_root=tmp_path / "state",
            now=lambda: NOW,
        )
