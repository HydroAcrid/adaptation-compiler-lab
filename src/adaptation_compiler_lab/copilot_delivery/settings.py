"""Digest-bound installation of Temper's dedicated Copilot CLI user hook."""

from __future__ import annotations

import base64
import difflib
import json
import os
import secrets
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.copilot_delivery.models import (
    CopilotHookFileChangeReceiptV1,
    CopilotHookFilePreviewV1,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_PREVIEW_TTL = timedelta(minutes=15)
_ROLLBACK_TTL = timedelta(days=30)
_MAX_HOOK_FILE_BYTES = 256 * 1024


class CopilotHookFileError(ValueError):
    """Raised when the owned Copilot hook file cannot be changed exactly."""


@dataclass(frozen=True, slots=True)
class _FileState:
    existed: bool
    payload: bytes


@dataclass(frozen=True, slots=True)
class _PreviewState:
    preview: CopilotHookFilePreviewV1
    hook_path: Path
    helper_path: Path
    before: _FileState
    after: _FileState


@dataclass(frozen=True, slots=True)
class _ReceiptState:
    receipt: CopilotHookFileChangeReceiptV1
    hook_path: Path
    backup: RawPayloadRef


class CopilotHookFileService:
    """Own one explicit ``temper.json`` hook file and nothing else."""

    def __init__(
        self,
        *,
        raw_store: LocalRawPayloadStore,
        signer: GovernanceSigner,
        now: Callable[[], datetime],
        state_root: Path,
    ) -> None:
        if not raw_store.encrypted:
            raise CopilotHookFileError("Copilot hook backups require encrypted storage")
        self._raw_store = raw_store
        self._signer = signer
        self._now = now
        self._state_root = state_root.expanduser().resolve()
        self._previews: dict[str, _PreviewState] = {}
        self._receipts: dict[str, _ReceiptState] = {}
        self._idempotency: dict[str, tuple[str, CopilotHookFileChangeReceiptV1]] = {}
        self._rolled_back: set[str] = set()
        self._load()

    def preview(
        self,
        *,
        operation: Literal["install", "uninstall"],
        hook_path: Path,
        helper_path: Path,
    ) -> CopilotHookFilePreviewV1:
        hook = hook_path.expanduser().resolve(strict=False)
        helper = helper_path.expanduser().resolve(strict=True)
        if hook.name != "temper.json" or hook.parent.name != "hooks":
            raise CopilotHookFileError("Copilot hook path is not product-owned")
        if not helper.is_file():
            raise CopilotHookFileError("Temper hook helper is unavailable")
        before = _read_file(hook)
        after = (
            _FileState(existed=True, payload=_hook_payload(helper))
            if operation == "install"
            else _FileState(existed=False, payload=b"")
        )
        redacted_before = (
            _display(before).decode("utf-8").replace(str(helper), "<Temper hook helper>")
        )
        redacted_after = (
            _display(after).decode("utf-8").replace(str(helper), "<Temper hook helper>")
        )
        diff = (
            "".join(
                difflib.unified_diff(
                    redacted_before.splitlines(keepends=True),
                    redacted_after.splitlines(keepends=True),
                    fromfile="a/Copilot user hooks/temper.json",
                    tofile="b/Copilot user hooks/temper.json",
                )
            )
            or "No change: Temper's dedicated Copilot hook file already matches this request."
        )
        token = f"copilot-hook-{secrets.token_hex(12)}"
        preview = CopilotHookFilePreviewV1(
            preview_token=token,
            operation=operation,
            before_digest=_state_digest(before),
            after_digest=_state_digest(after),
            before_existed=before.existed,
            after_existed=after.existed,
            helper_digest=_digest(helper.read_bytes()),
            redacted_diff=diff,
            expires_at=self._now() + _PREVIEW_TTL,
        )
        self._previews[token] = _PreviewState(preview, hook, helper, before, after)
        return preview

    def apply(
        self,
        *,
        preview_token: str,
        expected_before_digest: str,
        idempotency_key: str,
    ) -> CopilotHookFileChangeReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "apply_copilot_hook_file",
                "before": expected_before_digest,
                "preview_token": preview_token,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        state = self._previews.get(preview_token)
        if state is None or state.preview.expires_at <= self._now():
            raise CopilotHookFileError("Copilot hook preview expired")
        if state.preview.before_digest != expected_before_digest:
            raise CopilotHookFileError("Copilot hook preview digest changed")
        if _state_digest(_read_file(state.hook_path)) != expected_before_digest:
            raise CopilotHookFileError("Copilot hook file changed after preview")
        if _digest(state.helper_path.read_bytes()) != state.preview.helper_digest:
            raise CopilotHookFileError("Temper hook helper changed after preview")
        backup = self._raw_store.put(
            state.before.payload,
            media_type="application/vnd.temper.copilot-hook-backup",
        )
        _write_file(state.hook_path, state.after)
        if _state_digest(_read_file(state.hook_path)) != state.preview.after_digest:
            _write_file(state.hook_path, state.before)
            raise CopilotHookFileError("Copilot hook write failed verification")
        receipt = self._signed_receipt(
            preview=state.preview,
            operation=state.preview.operation,
            backup=backup,
            applied_at=self._now(),
            hook_path=state.hook_path,
        )
        try:
            self._append(
                receipt,
                backup=backup,
                hook_path=state.hook_path,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except (OSError, TypeError, ValueError) as error:
            _write_file(state.hook_path, state.before)
            raise CopilotHookFileError("Copilot hook receipt could not be persisted") from error
        self._receipts[receipt.receipt_id] = _ReceiptState(receipt, state.hook_path, backup)
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        return receipt

    def rollback(
        self,
        *,
        receipt_id: str,
        expected_current_digest: str,
        idempotency_key: str,
    ) -> CopilotHookFileChangeReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "rollback_copilot_hook_file",
                "current": expected_current_digest,
                "receipt_id": receipt_id,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        state = self._receipts.get(receipt_id)
        if (
            state is None
            or receipt_id in self._rolled_back
            or state.receipt.rollback_available_until <= self._now()
        ):
            raise CopilotHookFileError("Copilot hook rollback is unavailable")
        current = _read_file(state.hook_path)
        if (
            _state_digest(current) != expected_current_digest
            or expected_current_digest != state.receipt.after_digest
        ):
            raise CopilotHookFileError("Copilot hook changed after installation")
        original = _FileState(
            existed=state.receipt.before_existed,
            payload=self._raw_store.read(state.backup),
        )
        _write_file(state.hook_path, original)
        if _state_digest(_read_file(state.hook_path)) != state.receipt.before_digest:
            _write_file(state.hook_path, current)
            raise CopilotHookFileError("Copilot hook rollback failed verification")
        now = self._now()
        placeholder = CopilotHookFilePreviewV1(
            preview_token=state.receipt.preview_token,
            operation="uninstall" if state.receipt.operation == "install" else "install",
            before_digest=state.receipt.after_digest,
            after_digest=state.receipt.before_digest,
            before_existed=state.receipt.after_existed,
            after_existed=state.receipt.before_existed,
            helper_digest=state.receipt.helper_digest,
            redacted_diff="Rollback restores the exact encrypted original bytes.",
            expires_at=now + _PREVIEW_TTL,
        )
        receipt = self._signed_receipt(
            preview=placeholder,
            operation="rollback",
            backup=state.backup,
            applied_at=now,
            hook_path=state.hook_path,
            rollback_of_receipt_id=receipt_id,
        )
        try:
            self._append(
                receipt,
                backup=state.backup,
                hook_path=state.hook_path,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except (OSError, TypeError, ValueError) as error:
            _write_file(state.hook_path, current)
            raise CopilotHookFileError("Copilot rollback receipt could not be persisted") from error
        self._rolled_back.add(receipt_id)
        self._receipts[receipt.receipt_id] = _ReceiptState(receipt, state.hook_path, state.backup)
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        return receipt

    def receipt_is_current(self, receipt_id: str, *, helper_path: Path) -> bool:
        state = self._receipts.get(receipt_id)
        if state is None:
            return False
        try:
            helper = helper_path.expanduser().resolve(strict=True)
            return (
                _digest(helper.read_bytes()) == state.receipt.helper_digest
                and _state_digest(_read_file(state.hook_path)) == state.receipt.after_digest
            )
        except OSError:
            return False

    def verified_receipt(self, receipt_id: str) -> CopilotHookFileChangeReceiptV1:
        """Return one persisted receipt only after its index was verified at load time."""

        state = self._receipts.get(receipt_id)
        if state is None:
            raise CopilotHookFileError("Copilot hook receipt is unavailable")
        return state.receipt

    def _signed_receipt(
        self,
        *,
        preview: CopilotHookFilePreviewV1,
        operation: Literal["install", "uninstall", "rollback"],
        backup: RawPayloadRef,
        applied_at: datetime,
        hook_path: Path,
        rollback_of_receipt_id: str | None = None,
    ) -> CopilotHookFileChangeReceiptV1:
        placeholder = self._signer.envelope(
            {}, purpose="copilot_hook_file_change", signed_at=applied_at
        )
        draft = CopilotHookFileChangeReceiptV1(
            receipt_id=f"copilot-hook-change-{secrets.token_hex(12)}",
            preview_token=preview.preview_token,
            operation=operation,
            before_digest=preview.before_digest,
            after_digest=preview.after_digest,
            before_existed=preview.before_existed,
            after_existed=preview.after_existed,
            helper_digest=preview.helper_digest,
            hook_file_locator_digest=_locator_digest(hook_path),
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
                    purpose="copilot_hook_file_change",
                    signed_at=applied_at,
                )
            }
        )

    @property
    def _index_path(self) -> Path:
        return self._state_root / "copilot-delivery" / "hook-file-receipts.json"

    def _append(
        self,
        receipt: CopilotHookFileChangeReceiptV1,
        *,
        backup: RawPayloadRef,
        hook_path: Path,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> None:
        value = self._read_index()
        entries = value["entries"]
        if not isinstance(entries, list):
            raise CopilotHookFileError("Copilot hook receipt index is invalid")
        entries.append(
            {
                "backup": {
                    "media_type": backup.media_type,
                    "relative_path": backup.relative_path,
                    "sha256": backup.sha256,
                    "size_bytes": backup.size_bytes,
                },
                "hook_path": str(hook_path),
                "idempotency_key": idempotency_key,
                "receipt": receipt.model_dump(mode="json"),
                "request_fingerprint": request_fingerprint,
            }
        )
        _atomic_replace(self._index_path, (canonical_json(value) + "\n").encode())

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        value = self._read_index()
        entries = value["entries"]
        if not isinstance(entries, list):
            raise CopilotHookFileError("Copilot hook receipt index is invalid")
        for raw in entries:
            try:
                if not isinstance(raw, dict) or not isinstance(raw["backup"], dict):
                    raise ValueError
                receipt = CopilotHookFileChangeReceiptV1.model_validate_json(
                    canonical_json(raw["receipt"]), strict=True
                )
                backup_raw = raw["backup"]
                backup = RawPayloadRef(
                    sha256=str(backup_raw["sha256"]),
                    size_bytes=int(backup_raw["size_bytes"]),
                    media_type=str(backup_raw["media_type"]),
                    relative_path=str(backup_raw["relative_path"]),
                )
                hook_path = Path(str(raw["hook_path"])).expanduser().resolve(strict=False)
                if (
                    receipt.hook_file_locator_digest != _locator_digest(hook_path)
                    or receipt.backup_digest != f"sha256:{backup.sha256}"
                ):
                    raise ValueError
                public_key = base64.b64encode(
                    self._signer.private_key.public_key().public_bytes_raw()
                ).decode("ascii")
                verify_detached_envelope(
                    receipt.unsigned_payload,
                    receipt.signature,
                    public_key_base64=public_key,
                    expected_purpose="copilot_hook_file_change",
                )
                key = str(raw["idempotency_key"])
                fingerprint = str(raw["request_fingerprint"])
            except (KeyError, TypeError, ValueError) as error:
                raise CopilotHookFileError(
                    "Copilot hook receipt index failed verification"
                ) from error
            if receipt.rollback_of_receipt_id:
                self._rolled_back.add(receipt.rollback_of_receipt_id)
            self._receipts[receipt.receipt_id] = _ReceiptState(receipt, hook_path, backup)
            self._idempotency[key] = (fingerprint, receipt)

    def _read_index(self) -> dict[str, object]:
        if not self._index_path.exists():
            return {"entries": [], "version": 1}
        try:
            value = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CopilotHookFileError("Copilot hook receipt index is invalid") from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise CopilotHookFileError("Copilot hook receipt index is invalid")
        return value

    def _replay(
        self, idempotency_key: str, fingerprint: str
    ) -> CopilotHookFileChangeReceiptV1 | None:
        previous = self._idempotency.get(idempotency_key)
        if previous is None:
            return None
        if previous[0] != fingerprint:
            raise CopilotHookFileError("idempotency key was reused for another hook change")
        return previous[1]


def _hook_payload(helper: Path) -> bytes:
    document = {
        "hooks": {
            "userPromptTransformed": [
                {
                    "args": [],
                    "exec": str(helper),
                    "timeoutSec": 1,
                    "type": "command",
                }
            ]
        },
        "version": 1,
    }
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read_file(path: Path) -> _FileState:
    if not path.exists():
        return _FileState(False, b"")
    if not path.is_file() or path.stat().st_size > _MAX_HOOK_FILE_BYTES:
        raise CopilotHookFileError("Copilot hook file is unavailable or oversized")
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CopilotHookFileError("Copilot hook file is not valid JSON") from error
    if not isinstance(value, dict):
        raise CopilotHookFileError("Copilot hook file must contain a JSON object")
    return _FileState(True, payload)


def _write_file(path: Path, state: _FileState) -> None:
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


def _display(state: _FileState) -> bytes:
    return state.payload if state.existed else b"{}\n"


def _digest(payload: bytes) -> str:
    return f"sha256:{sha256(payload).hexdigest()}"


def _state_digest(state: _FileState) -> str:
    return canonical_digest({"exists": state.existed, "payload_digest": _digest(state.payload)})


def _locator_digest(path: Path) -> str:
    return canonical_digest({"copilot_user_hook": str(path)})
