from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.copilot_delivery import (
    CopilotHookFileError,
    CopilotHookFileService,
)
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def _parts(tmp_path: Path) -> tuple[CopilotHookFileService, Path, Path, GovernanceSigner]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-owner-key",
        subject_id="temper-owner",
    )
    service = CopilotHookFileService(
        raw_store=LocalRawPayloadStore(
            tmp_path / "raw", encryption_key=RawEncryptionKey(b"c" * 32)
        ),
        signer=signer,
        now=lambda: NOW,
        state_root=tmp_path / "state",
    )
    hook = tmp_path / ".copilot" / "hooks" / "temper.json"
    helper = tmp_path / "Temper" / "temper-hook.exe"
    helper.parent.mkdir()
    helper.write_bytes(b"signed synthetic helper")
    return service, hook, helper, signer


def test_owned_hook_file_uses_direct_exec_and_exact_event_then_rolls_back(
    tmp_path: Path,
) -> None:
    service, hook, helper, _signer = _parts(tmp_path)
    hook.parent.mkdir(parents=True)
    original = b'{"version":1,"hooks":{"notification":[]}}\n'
    hook.write_bytes(original)

    preview = service.preview(operation="install", hook_path=hook, helper_path=helper)
    assert str(helper) not in preview.redacted_diff
    receipt = service.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="install",
    )
    document = cast(dict[str, Any], json.loads(hook.read_text(encoding="utf-8")))
    assert set(document) == {"hooks", "version"}
    assert set(document["hooks"]) == {"userPromptTransformed"}
    handler = document["hooks"]["userPromptTransformed"][0]
    assert handler == {
        "args": [],
        "exec": str(helper),
        "timeoutSec": 1,
        "type": "command",
    }
    assert not {"bash", "command", "env", "powershell"} & set(handler)

    service.rollback(
        receipt_id=receipt.receipt_id,
        expected_current_digest=receipt.after_digest,
        idempotency_key="rollback",
    )
    assert hook.read_bytes() == original


def test_hook_change_is_idempotent_restart_safe_and_race_protected(tmp_path: Path) -> None:
    service, hook, helper, signer = _parts(tmp_path)
    preview = service.preview(operation="install", hook_path=hook, helper_path=helper)
    receipt = service.apply(
        preview_token=preview.preview_token,
        expected_before_digest=preview.before_digest,
        idempotency_key="same",
    )
    assert (
        service.apply(
            preview_token=preview.preview_token,
            expected_before_digest=preview.before_digest,
            idempotency_key="same",
        )
        == receipt
    )

    restarted = CopilotHookFileService(
        raw_store=LocalRawPayloadStore(
            tmp_path / "raw", encryption_key=RawEncryptionKey(b"c" * 32)
        ),
        signer=signer,
        now=lambda: NOW,
        state_root=tmp_path / "state",
    )
    assert restarted.receipt_is_current(receipt.receipt_id, helper_path=helper)
    uninstall = restarted.preview(operation="uninstall", hook_path=hook, helper_path=helper)
    hook.write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(CopilotHookFileError, match="changed after preview"):
        restarted.apply(
            preview_token=uninstall.preview_token,
            expected_before_digest=uninstall.before_digest,
            idempotency_key="raced",
        )


def test_hook_service_rejects_unowned_path_or_plaintext_backup(tmp_path: Path) -> None:
    service, _hook, helper, signer = _parts(tmp_path)
    with pytest.raises(CopilotHookFileError, match="product-owned"):
        service.preview(
            operation="install",
            hook_path=tmp_path / ".copilot" / "settings.json",
            helper_path=helper,
        )
    with pytest.raises(CopilotHookFileError, match="encrypted"):
        CopilotHookFileService(
            raw_store=LocalRawPayloadStore.legacy_v1_synthetic(tmp_path / "plain"),
            signer=signer,
            now=lambda: NOW,
            state_root=tmp_path / "state-two",
        )
