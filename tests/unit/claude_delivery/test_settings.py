from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.claude_delivery import ClaudeHookSettingsService
from adaptation_compiler_lab.claude_delivery.settings import ClaudeHookSettingsError
from adaptation_compiler_lab.governance.signing import GovernanceSigner, verify_detached_envelope
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey

NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


def _service(tmp_path: Path) -> tuple[ClaudeHookSettingsService, GovernanceSigner]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-owner-key",
        subject_id="temper-owner",
    )
    raw_store = LocalRawPayloadStore(
        tmp_path / "raw",
        encryption_key=RawEncryptionKey(b"a" * 32),
    )
    return (
        ClaudeHookSettingsService(
            raw_store=raw_store,
            signer=signer,
            now=lambda: NOW,
            state_root=tmp_path / "state",
        ),
        signer,
    )


def _helper(tmp_path: Path) -> Path:
    path = tmp_path / "Temper" / "temper-hook.exe"
    path.parent.mkdir()
    path.write_bytes(b"synthetic signed helper")
    return path


def test_install_preserves_unrelated_settings_and_hooks_and_is_reversible(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    original: dict[str, Any] = {
        "permissions": {"allow": ["Read"]},
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/existing/audit",
                            "args": ["--safe"],
                            "timeout": 2,
                        }
                    ]
                }
            ]
        },
    }
    original_bytes = (json.dumps(original, indent=2) + "\n").encode()
    settings.write_bytes(original_bytes)
    helper = _helper(tmp_path)
    service, signer = _service(tmp_path)

    preview = service.preview(operation="install", settings_path=settings, helper_path=helper)
    assert str(helper) not in preview.redacted_diff
    assert "<Temper hook helper>" in preview.redacted_diff
    receipt = service.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="install-1",
    )
    installed = cast(dict[str, Any], json.loads(settings.read_text(encoding="utf-8")))
    assert installed["permissions"] == original["permissions"]
    assert installed["hooks"]["Stop"][0] == original["hooks"]["Stop"][0]
    for event in ("SessionEnd", "Stop", "StopFailure", "UserPromptSubmit"):
        assert any(
            handler.get("command") == str(helper)
            for group in installed["hooks"][event]
            for handler in group["hooks"]
        )
    verify_detached_envelope(
        receipt.unsigned_payload,
        receipt.signature,
        public_key_base64=__import__("base64")
        .b64encode(signer.private_key.public_key().public_bytes_raw())
        .decode(),
        expected_purpose="claude_hook_settings_change",
    )

    rolled_back = service.rollback(
        receipt_id=receipt.receipt_id,
        expected_current_digest=receipt.after_digest,
        idempotency_key="rollback-1",
    )
    assert rolled_back.rollback_of_receipt_id == receipt.receipt_id
    assert settings.read_bytes() == original_bytes


def test_install_is_idempotent_and_uninstall_removes_only_temper_handlers(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{"theme": "dark"}\n', encoding="utf-8")
    helper = _helper(tmp_path)
    service, _signer = _service(tmp_path)
    preview = service.preview(operation="install", settings_path=settings, helper_path=helper)
    first = service.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="same-request",
    )
    replay = service.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="same-request",
    )
    assert replay == first

    uninstall = service.preview(
        operation="uninstall",
        settings_path=settings,
        helper_path=helper,
    )
    service.apply(
        preview_token=uninstall.preview_token,
        expected_before_digest=uninstall.before_digest,
        idempotency_key="uninstall-1",
    )
    assert json.loads(settings.read_text(encoding="utf-8")) == {"theme": "dark"}


def test_receipts_replay_after_restart_and_restore_missing_settings_file(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    helper = _helper(tmp_path)
    service, signer = _service(tmp_path)
    preview = service.preview(operation="install", settings_path=settings, helper_path=helper)
    assert preview.before_existed is False
    assert preview.after_existed is True
    installed = service.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="durable-install",
    )
    assert settings.exists()

    restarted = ClaudeHookSettingsService(
        raw_store=LocalRawPayloadStore(
            tmp_path / "raw",
            encryption_key=RawEncryptionKey(b"a" * 32),
        ),
        signer=signer,
        now=lambda: NOW,
        state_root=tmp_path / "state",
    )
    replay = restarted.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="durable-install",
    )
    assert replay == installed
    restarted.rollback(
        receipt_id=installed.receipt_id,
        expected_current_digest=installed.after_digest,
        idempotency_key="durable-rollback",
    )
    assert not settings.exists()

    restarted_again = ClaudeHookSettingsService(
        raw_store=LocalRawPayloadStore(
            tmp_path / "raw",
            encryption_key=RawEncryptionKey(b"a" * 32),
        ),
        signer=signer,
        now=lambda: NOW,
        state_root=tmp_path / "state",
    )
    rollback_replay = restarted_again.rollback(
        receipt_id=installed.receipt_id,
        expected_current_digest=installed.after_digest,
        idempotency_key="durable-rollback",
    )
    assert rollback_replay.rollback_of_receipt_id == installed.receipt_id


def test_persisted_receipt_tampering_fails_closed(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    helper = _helper(tmp_path)
    service, signer = _service(tmp_path)
    preview = service.preview(operation="install", settings_path=settings, helper_path=helper)
    service.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="tamper-install",
    )
    index_path = tmp_path / "state" / "claude-delivery" / "settings-change-receipts.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["entries"][0]["receipt"]["after_existed"] = False
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ClaudeHookSettingsError, match="failed verification"):
        ClaudeHookSettingsService(
            raw_store=LocalRawPayloadStore(
                tmp_path / "raw",
                encryption_key=RawEncryptionKey(b"a" * 32),
            ),
            signer=signer,
            now=lambda: NOW,
            state_root=tmp_path / "state",
        )


def test_stale_settings_or_changed_helper_fails_before_write(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text("{}\n", encoding="utf-8")
    helper = _helper(tmp_path)
    service, _signer = _service(tmp_path)
    preview = service.preview(operation="install", settings_path=settings, helper_path=helper)
    settings.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ClaudeHookSettingsError, match="changed after preview"):
        service.apply(
            preview_token=preview.preview_token,
            expected_before_digest=preview.before_digest,
            idempotency_key="stale-settings",
        )
    assert json.loads(settings.read_text()) == {"changed": True}

    preview = service.preview(operation="install", settings_path=settings, helper_path=helper)
    helper.write_bytes(b"changed helper")
    with pytest.raises(ClaudeHookSettingsError, match="helper changed"):
        service.apply(
            preview_token=preview.preview_token,
            expected_before_digest=preview.before_digest,
            idempotency_key="stale-helper",
        )


def test_invalid_or_oversized_settings_and_plaintext_backup_are_rejected(tmp_path: Path) -> None:
    helper = _helper(tmp_path)
    service, signer = _service(tmp_path)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(ClaudeHookSettingsError, match="JSON object"):
        service.preview(operation="install", settings_path=invalid, helper_path=helper)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (256 * 1024 + 1))
    with pytest.raises(ClaudeHookSettingsError, match="oversized"):
        service.preview(operation="install", settings_path=oversized, helper_path=helper)

    with pytest.raises(ClaudeHookSettingsError, match="encrypted"):
        ClaudeHookSettingsService(
            raw_store=LocalRawPayloadStore.legacy_v1_synthetic(tmp_path / "plain"),
            signer=signer,
            now=lambda: NOW,
            state_root=tmp_path / "state",
        )
