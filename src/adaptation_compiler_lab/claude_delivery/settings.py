"""Previewed and reversible installation of Temper-owned Claude user hooks."""

from __future__ import annotations

import base64
import difflib
import json
import os
import secrets
import tempfile
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.claude_delivery.models import (
    ClaudeHookEvent,
    ClaudeHookSettingsChangeReceiptV1,
    ClaudeHookSettingsPreviewV1,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_PREVIEW_TTL = timedelta(minutes=15)
_ROLLBACK_TTL = timedelta(days=30)
_MAX_SETTINGS_BYTES = 256 * 1024
_EVENTS = tuple(sorted(ClaudeHookEvent, key=lambda item: item.value))


class ClaudeHookSettingsError(ValueError):
    """Raised when a Claude settings change cannot be applied exactly and safely."""


@dataclass(frozen=True, slots=True)
class _PreviewState:
    preview: ClaudeHookSettingsPreviewV1
    settings_path: Path
    helper_path: Path
    before: _SettingsState
    after: _SettingsState


@dataclass(frozen=True, slots=True)
class _ReceiptState:
    receipt: ClaudeHookSettingsChangeReceiptV1
    settings_path: Path
    backup: RawPayloadRef


@dataclass(frozen=True, slots=True)
class _SettingsState:
    existed: bool
    payload: bytes


class ClaudeHookSettingsService:
    """Own only Temper's exact hook handlers inside Claude's user settings."""

    def __init__(
        self,
        *,
        raw_store: LocalRawPayloadStore,
        signer: GovernanceSigner,
        now: Callable[[], datetime],
        state_root: Path,
    ) -> None:
        if not raw_store.encrypted:
            raise ClaudeHookSettingsError("Claude settings backups require encrypted storage")
        self._raw_store = raw_store
        self._signer = signer
        self._now = now
        self._state_root = state_root.expanduser().resolve()
        self._previews: dict[str, _PreviewState] = {}
        self._receipts: dict[str, _ReceiptState] = {}
        self._idempotency: dict[str, tuple[str, ClaudeHookSettingsChangeReceiptV1]] = {}
        self._rolled_back: set[str] = set()
        self._load_receipts()

    def preview(
        self,
        *,
        operation: Literal["install", "uninstall"],
        settings_path: Path,
        helper_path: Path,
    ) -> ClaudeHookSettingsPreviewV1:
        settings = settings_path.expanduser().resolve(strict=False)
        helper = helper_path.expanduser().resolve(strict=True)
        if not helper.is_file():
            raise ClaudeHookSettingsError("Temper hook helper is unavailable")
        before = _read_settings(settings)
        document = _parse_settings(before.payload) if before.existed else {}
        updated = _updated_document(
            document,
            helper=helper,
            install=operation == "install",
        )
        after_existed = operation == "install" or before.existed
        after = _SettingsState(
            existed=after_existed,
            payload=(
                _encode_settings(updated, newline=_newline(before.payload))
                if after_existed
                else b""
            ),
        )
        helper_digest = _digest(helper.read_bytes())
        redacted_before = _redact_helper(_display_payload(before).decode("utf-8"), helper)
        redacted_after = _redact_helper(_display_payload(after).decode("utf-8"), helper)
        diff = "".join(
            difflib.unified_diff(
                redacted_before.splitlines(keepends=True),
                redacted_after.splitlines(keepends=True),
                fromfile="a/Claude user settings",
                tofile="b/Claude user settings",
            )
        )
        if not diff:
            diff = "No change: Temper's exact Claude hook entries already match this request."
        token = f"claude-settings-{secrets.token_hex(12)}"
        preview = ClaudeHookSettingsPreviewV1(
            preview_token=token,
            operation=operation,
            before_digest=_state_digest(before),
            after_digest=_state_digest(after),
            before_existed=before.existed,
            after_existed=after.existed,
            helper_digest=helper_digest,
            events=_EVENTS,
            redacted_diff=diff,
            expires_at=self._now() + _PREVIEW_TTL,
        )
        self._previews[token] = _PreviewState(
            preview=preview,
            settings_path=settings,
            helper_path=helper,
            before=before,
            after=after,
        )
        return preview

    def apply(
        self,
        *,
        preview_token: str,
        expected_before_digest: str,
        idempotency_key: str,
    ) -> ClaudeHookSettingsChangeReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "apply_claude_hook_settings",
                "before": expected_before_digest,
                "preview_token": preview_token,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        state = self._previews.get(preview_token)
        if state is None or state.preview.expires_at <= self._now():
            raise ClaudeHookSettingsError("Claude settings preview expired")
        if state.preview.before_digest != expected_before_digest:
            raise ClaudeHookSettingsError("Claude settings preview digest changed")
        if _state_digest(_read_settings(state.settings_path)) != expected_before_digest:
            raise ClaudeHookSettingsError("Claude settings changed after preview")
        if _digest(state.helper_path.read_bytes()) != state.preview.helper_digest:
            raise ClaudeHookSettingsError("Temper hook helper changed after preview")
        backup = self._raw_store.put(
            state.before.payload,
            media_type="application/vnd.temper.claude-settings-backup",
        )
        _write_settings(state.settings_path, state.after)
        if _state_digest(_read_settings(state.settings_path)) != state.preview.after_digest:
            _write_settings(state.settings_path, state.before)
            raise ClaudeHookSettingsError("Claude settings write failed verification")
        receipt = self._signed_receipt(
            preview=state.preview,
            operation=state.preview.operation,
            backup=backup,
            applied_at=self._now(),
            settings_path=state.settings_path,
        )
        self._receipts[receipt.receipt_id] = _ReceiptState(
            receipt=receipt,
            settings_path=state.settings_path,
            backup=backup,
        )
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        try:
            self._persist_receipt(
                receipt,
                backup=backup,
                settings_path=state.settings_path,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except (OSError, TypeError, ValueError) as error:
            _write_settings(state.settings_path, state.before)
            self._receipts.pop(receipt.receipt_id, None)
            self._idempotency.pop(idempotency_key, None)
            raise ClaudeHookSettingsError(
                "Claude settings receipt could not be persisted"
            ) from error
        return receipt

    def rollback(
        self,
        *,
        receipt_id: str,
        expected_current_digest: str,
        idempotency_key: str,
    ) -> ClaudeHookSettingsChangeReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "rollback_claude_hook_settings",
                "current": expected_current_digest,
                "receipt_id": receipt_id,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        state = self._receipts.get(receipt_id)
        if state is None or receipt_id in self._rolled_back:
            raise ClaudeHookSettingsError("Claude settings rollback is unavailable")
        if state.receipt.rollback_available_until <= self._now():
            raise ClaudeHookSettingsError("Claude settings rollback expired")
        current = _read_settings(state.settings_path)
        if (
            _state_digest(current) != expected_current_digest
            or expected_current_digest != state.receipt.after_digest
        ):
            raise ClaudeHookSettingsError("Claude settings changed after hook installation")
        original = self._raw_store.read(state.backup)
        restored = _SettingsState(
            existed=state.receipt.before_existed,
            payload=original,
        )
        _write_settings(state.settings_path, restored)
        if _state_digest(_read_settings(state.settings_path)) != state.receipt.before_digest:
            _write_settings(state.settings_path, current)
            raise ClaudeHookSettingsError("Claude settings rollback failed verification")
        now = self._now()
        placeholder = ClaudeHookSettingsPreviewV1(
            preview_token=state.receipt.preview_token,
            operation="uninstall" if state.receipt.operation == "install" else "install",
            before_digest=state.receipt.after_digest,
            after_digest=state.receipt.before_digest,
            before_existed=state.receipt.after_existed,
            after_existed=state.receipt.before_existed,
            helper_digest=state.receipt.helper_digest,
            events=_EVENTS,
            redacted_diff="Rollback restores the exact encrypted original bytes.",
            expires_at=now + _PREVIEW_TTL,
        )
        rolled_back = self._signed_receipt(
            preview=placeholder,
            operation="rollback",
            backup=state.backup,
            applied_at=now,
            settings_path=state.settings_path,
            rollback_of_receipt_id=receipt_id,
        )
        self._rolled_back.add(receipt_id)
        self._receipts[rolled_back.receipt_id] = _ReceiptState(
            receipt=rolled_back,
            settings_path=state.settings_path,
            backup=state.backup,
        )
        self._idempotency[idempotency_key] = (fingerprint, rolled_back)
        try:
            self._persist_receipt(
                rolled_back,
                backup=state.backup,
                settings_path=state.settings_path,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except (OSError, TypeError, ValueError) as error:
            _write_settings(state.settings_path, current)
            self._rolled_back.discard(receipt_id)
            self._receipts.pop(rolled_back.receipt_id, None)
            self._idempotency.pop(idempotency_key, None)
            raise ClaudeHookSettingsError(
                "Claude settings rollback receipt could not be persisted"
            ) from error
        return rolled_back

    def _signed_receipt(
        self,
        *,
        preview: ClaudeHookSettingsPreviewV1,
        operation: Literal["install", "uninstall", "rollback"],
        backup: RawPayloadRef,
        applied_at: datetime,
        settings_path: Path,
        rollback_of_receipt_id: str | None = None,
    ) -> ClaudeHookSettingsChangeReceiptV1:
        placeholder = self._signer.envelope(
            {}, purpose="claude_hook_settings_change", signed_at=applied_at
        )
        draft = ClaudeHookSettingsChangeReceiptV1(
            receipt_id=f"claude-settings-change-{secrets.token_hex(12)}",
            preview_token=preview.preview_token,
            operation=operation,
            before_digest=preview.before_digest,
            after_digest=preview.after_digest,
            before_existed=preview.before_existed,
            after_existed=preview.after_existed,
            helper_digest=preview.helper_digest,
            settings_locator_digest=_settings_locator_digest(settings_path),
            backup_digest=f"sha256:{backup.sha256}",
            applied_at=applied_at,
            rollback_available_until=applied_at + _ROLLBACK_TTL,
            rollback_of_receipt_id=rollback_of_receipt_id,
            signature=placeholder,
        )
        return draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="claude_hook_settings_change",
                    signed_at=applied_at,
                )
            }
        )

    @property
    def _receipt_index_path(self) -> Path:
        return self._state_root / "claude-delivery" / "settings-change-receipts.json"

    def _persist_receipt(
        self,
        receipt: ClaudeHookSettingsChangeReceiptV1,
        *,
        backup: RawPayloadRef,
        settings_path: Path,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> None:
        path = self._receipt_index_path
        path.parent.mkdir(parents=True, exist_ok=True)
        value = self._read_receipt_index()
        entries = value.setdefault("entries", [])
        if not isinstance(entries, list):
            raise ClaudeHookSettingsError("Claude settings receipt index is invalid")
        entries.append(
            {
                "backup": {
                    "media_type": backup.media_type,
                    "relative_path": backup.relative_path,
                    "sha256": backup.sha256,
                    "size_bytes": backup.size_bytes,
                },
                "idempotency_key": idempotency_key,
                "receipt": receipt.model_dump(mode="json"),
                "request_fingerprint": request_fingerprint,
                "settings_path": str(settings_path),
            }
        )
        _atomic_replace(path, (canonical_json(value) + "\n").encode("utf-8"))

    def _load_receipts(self) -> None:
        path = self._receipt_index_path
        if not path.exists():
            return
        value = self._read_receipt_index()
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise ClaudeHookSettingsError("Claude settings receipt index is invalid")
        loaded: list[tuple[ClaudeHookSettingsChangeReceiptV1, RawPayloadRef, Path, str, str]] = []
        for raw in entries:
            try:
                if not isinstance(raw, dict):
                    raise ValueError
                receipt = ClaudeHookSettingsChangeReceiptV1.model_validate_json(
                    canonical_json(raw["receipt"]), strict=True
                )
                backup_raw = raw["backup"]
                if not isinstance(backup_raw, dict):
                    raise ValueError
                backup = RawPayloadRef(
                    sha256=str(backup_raw["sha256"]),
                    size_bytes=int(backup_raw["size_bytes"]),
                    media_type=str(backup_raw["media_type"]),
                    relative_path=str(backup_raw["relative_path"]),
                )
                settings_path = Path(str(raw["settings_path"])).expanduser().resolve(strict=False)
                idempotency_key = str(raw["idempotency_key"])
                request_fingerprint = str(raw["request_fingerprint"])
                self._verify_receipt(receipt, settings_path=settings_path, backup=backup)
            except (KeyError, TypeError, ValueError) as error:
                raise ClaudeHookSettingsError(
                    "Claude settings receipt index failed verification"
                ) from error
            loaded.append((receipt, backup, settings_path, idempotency_key, request_fingerprint))
        for receipt, backup, settings_path, idempotency_key, request_fingerprint in loaded:
            if receipt.rollback_of_receipt_id is not None:
                self._rolled_back.add(receipt.rollback_of_receipt_id)
            self._receipts[receipt.receipt_id] = _ReceiptState(
                receipt=receipt,
                settings_path=settings_path,
                backup=backup,
            )
            self._idempotency[idempotency_key] = (request_fingerprint, receipt)

    def _read_receipt_index(self) -> dict[str, object]:
        path = self._receipt_index_path
        if not path.exists():
            return {"entries": [], "version": 1}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ClaudeHookSettingsError("Claude settings receipt index is invalid") from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ClaudeHookSettingsError("Claude settings receipt index is invalid")
        return value

    def _verify_receipt(
        self,
        receipt: ClaudeHookSettingsChangeReceiptV1,
        *,
        settings_path: Path,
        backup: RawPayloadRef,
    ) -> None:
        if receipt.settings_locator_digest != _settings_locator_digest(settings_path):
            raise ClaudeHookSettingsError("Claude settings receipt location changed")
        if receipt.backup_digest != f"sha256:{backup.sha256}":
            raise ClaudeHookSettingsError("Claude settings receipt backup changed")
        public_key = base64.b64encode(
            self._signer.private_key.public_key().public_bytes_raw()
        ).decode("ascii")
        verify_detached_envelope(
            receipt.unsigned_payload,
            receipt.signature,
            public_key_base64=public_key,
            expected_purpose="claude_hook_settings_change",
        )

    def _replay(
        self, idempotency_key: str, fingerprint: str
    ) -> ClaudeHookSettingsChangeReceiptV1 | None:
        previous = self._idempotency.get(idempotency_key)
        if previous is None:
            return None
        prior_fingerprint, receipt = previous
        if prior_fingerprint != fingerprint:
            raise ClaudeHookSettingsError("idempotency key was reused for another settings change")
        return receipt


def _read_settings(path: Path) -> _SettingsState:
    if not path.exists():
        return _SettingsState(existed=False, payload=b"")
    if not path.is_file() or path.stat().st_size > _MAX_SETTINGS_BYTES:
        raise ClaudeHookSettingsError("Claude user settings are unavailable or oversized")
    try:
        payload = path.read_bytes()
        payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ClaudeHookSettingsError("Claude user settings are not valid UTF-8") from error
    return _SettingsState(existed=True, payload=payload)


def _parse_settings(payload: bytes) -> dict[str, object]:
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ClaudeHookSettingsError("Claude user settings are not valid JSON") from error
    if not isinstance(document, dict):
        raise ClaudeHookSettingsError("Claude user settings must contain a JSON object")
    hooks = document.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        raise ClaudeHookSettingsError("Claude hooks settings have an unsupported shape")
    return document


def _updated_document(
    document: dict[str, object], *, helper: Path, install: bool
) -> dict[str, object]:
    updated = deepcopy(document)
    hooks_value = updated.setdefault("hooks", {})
    if not isinstance(hooks_value, dict):
        raise ClaudeHookSettingsError("Claude hooks settings have an unsupported shape")
    handler = {
        "type": "command",
        "command": str(helper),
        "args": [],
        "timeout": 5,
    }
    group = {"hooks": [handler]}
    for event in _EVENTS:
        key = event.value
        groups = hooks_value.get(key, [])
        if not isinstance(groups, list):
            raise ClaudeHookSettingsError("Claude hook event has an unsupported shape")
        cleaned: list[object] = []
        for existing in groups:
            if not isinstance(existing, dict):
                raise ClaudeHookSettingsError("Claude hook group has an unsupported shape")
            child_hooks = existing.get("hooks")
            if not isinstance(child_hooks, list):
                raise ClaudeHookSettingsError("Claude hook handlers have an unsupported shape")
            retained = [item for item in child_hooks if item != handler]
            if retained:
                preserved = dict(existing)
                preserved["hooks"] = retained
                cleaned.append(preserved)
        if install:
            cleaned.append(group)
        if cleaned:
            hooks_value[key] = cleaned
        else:
            hooks_value.pop(key, None)
    if not hooks_value:
        updated.pop("hooks", None)
    return updated


def _encode_settings(document: dict[str, object], *, newline: str) -> bytes:
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    return rendered.replace("\n", newline).encode("utf-8")


def _newline(payload: bytes) -> str:
    return "\r\n" if b"\r\n" in payload else "\n"


def _redact_helper(value: str, helper: Path) -> str:
    return value.replace(str(helper), "<Temper hook helper>")


def _digest(payload: bytes) -> str:
    return f"sha256:{sha256(payload).hexdigest()}"


def _state_digest(state: _SettingsState) -> str:
    return canonical_digest({"exists": state.existed, "payload_digest": _digest(state.payload)})


def _settings_locator_digest(path: Path) -> str:
    return canonical_digest({"claude_user_settings": str(path)})


def _display_payload(state: _SettingsState) -> bytes:
    return state.payload if state.existed else b"{}\n"


def _write_settings(path: Path, state: _SettingsState) -> None:
    if state.existed:
        _atomic_replace(path, state.payload)
    else:
        path.unlink(missing_ok=True)


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
