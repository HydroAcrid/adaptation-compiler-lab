"""Signed, previewed Copilot CLI delivery connection lifecycle."""

from __future__ import annotations

import base64
import json
import os
import secrets
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.copilot_delivery.models import (
    CopilotConnectionPreviewV1,
    CopilotConnectionProjectV1,
    CopilotConnectionReceiptV1,
    CopilotConnectionStatusV1,
    CopilotHookAuthorizationV1,
)
from adaptation_compiler_lab.copilot_delivery.settings import (
    CopilotHookFileError,
    CopilotHookFileService,
)
from adaptation_compiler_lab.domain import PermittedUse, Scope, Sha256Digest
from adaptation_compiler_lab.governance import ConsentReceipt, SignerIdentity, SourceSelector
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    sign_consent,
    verify_detached_envelope,
    verify_signed_governance,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_CONSENT_WINDOW = timedelta(days=30)


class CopilotConnectionError(ValueError):
    """Raised when Copilot CLI delivery cannot be connected exactly."""


@dataclass(frozen=True, slots=True)
class _HeldPreview:
    preview: CopilotConnectionPreviewV1
    projects: tuple[CopilotConnectionProjectV1, ...]


class CopilotConnectionService:
    """Bind explicit target-delivery consent to one owned Copilot hook file."""

    def __init__(
        self,
        *,
        subject_id: str,
        projects: Mapping[str, Sha256Digest],
        hook_files: CopilotHookFileService,
        hook_path: Path,
        helper_path: Path,
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
        state_root: Path,
        now: Callable[[], datetime],
    ) -> None:
        if not projects:
            raise CopilotConnectionError("Copilot requires a registered project")
        if (
            signer.subject_id != subject_id
            or signer_identity.subject_id != subject_id
            or signer.identity_id != signer_identity.identity_id
            or signer.fingerprint != signer_identity.key_fingerprint
        ):
            raise CopilotConnectionError("Copilot connection signer changed")
        verify_signed_governance(signer_identity)
        self._subject_id = subject_id
        self._projects = tuple(
            CopilotConnectionProjectV1(
                project_id=project_id,
                project_registration_digest=digest,
            )
            for project_id, digest in sorted(projects.items())
        )
        self._hook_files = hook_files
        self._hook_path = hook_path.expanduser().resolve(strict=False)
        self._helper_path = helper_path.expanduser().resolve(strict=False)
        self._signer = signer
        self._identity = signer_identity
        self._state_root = state_root.expanduser().resolve()
        self._now = now
        self._previews: dict[str, _HeldPreview] = {}
        self._receipts: list[CopilotConnectionReceiptV1] = []
        self._idempotency: dict[str, tuple[str, CopilotConnectionReceiptV1]] = {}
        self._load()

    def preview(self, *, operation: Literal["connect", "disconnect"]) -> CopilotConnectionPreviewV1:
        current = self._receipts[-1] if self._receipts else None
        if operation == "connect" and current is not None and current.operation == "connect":
            raise CopilotConnectionError("Copilot is already connected")
        if operation == "disconnect" and (current is None or current.operation != "connect"):
            raise CopilotConnectionError("Copilot is not connected")
        try:
            hook_file = self._hook_files.preview(
                operation="install" if operation == "connect" else "uninstall",
                hook_path=self._hook_path,
                helper_path=self._helper_path,
            )
        except (OSError, CopilotHookFileError) as error:
            raise CopilotConnectionError("Copilot user hook is unavailable") from error
        now = self._now()
        consent = current.consent if operation == "disconnect" and current else None
        preview = CopilotConnectionPreviewV1(
            operation=operation,
            hook_file=hook_file,
            project_ids=tuple(item.project_id for item in self._projects),
            current_connection_digest=None if current is None else current.content_digest,
            consent_expires_at=consent.expires_at if consent else now + _CONSENT_WINDOW,
            delivery_enabled=operation == "connect",
        )
        self._previews[hook_file.preview_token] = _HeldPreview(preview, self._projects)
        return preview

    def apply(
        self,
        *,
        preview_token: str,
        expected_before_digest: str,
        consent_confirmed: bool,
        idempotency_key: str,
    ) -> CopilotConnectionReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "apply_copilot_connection",
                "consent_confirmed": consent_confirmed,
                "expected_before_digest": expected_before_digest,
                "preview_token": preview_token,
            }
        )
        previous = self._idempotency.get(idempotency_key)
        if previous is not None:
            if previous[0] != fingerprint:
                raise CopilotConnectionError("idempotency key was reused")
            return previous[1]
        if not consent_confirmed:
            raise CopilotConnectionError("explicit Copilot connection consent is required")
        held = self._previews.get(preview_token)
        if held is None or held.preview.hook_file.before_digest != expected_before_digest:
            raise CopilotConnectionError("Copilot connection preview changed")
        current = self._receipts[-1] if self._receipts else None
        if held.preview.current_connection_digest != (
            None if current is None else current.content_digest
        ):
            raise CopilotConnectionError("Copilot connection changed after preview")
        now = self._now()
        consent = (
            self._issue_consent(now, held.projects)
            if held.preview.operation == "connect"
            else _disconnect_consent(current)
        )
        try:
            hook_receipt = self._hook_files.apply(
                preview_token=preview_token,
                expected_before_digest=expected_before_digest,
                idempotency_key=f"hook-{idempotency_key}",
            )
        except (OSError, CopilotHookFileError) as error:
            raise CopilotConnectionError("Copilot hook change was refused") from error
        placeholder = self._signer.envelope({}, purpose="copilot_connection_change", signed_at=now)
        draft = CopilotConnectionReceiptV1(
            receipt_id=f"copilot-connection-{secrets.token_hex(12)}",
            operation=held.preview.operation,
            subject_id=self._subject_id,
            projects=held.projects,
            consent=consent,
            hook_file_receipt=hook_receipt,
            previous_connection_digest=None if current is None else current.content_digest,
            delivery_enabled=held.preview.operation == "connect",
            occurred_at=now,
            expires_at=consent.expires_at,
            signature=placeholder,
        )
        receipt = draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="copilot_connection_change",
                    signed_at=now,
                )
            }
        )
        try:
            self._append(receipt, idempotency_key, fingerprint)
        except (OSError, TypeError, ValueError) as error:
            with suppress(OSError, CopilotHookFileError):
                self._hook_files.rollback(
                    receipt_id=hook_receipt.receipt_id,
                    expected_current_digest=hook_receipt.after_digest,
                    idempotency_key=f"connection-recovery-{idempotency_key}",
                )
            raise CopilotConnectionError(
                "Copilot connection receipt could not be persisted"
            ) from error
        self._receipts.append(receipt)
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        return receipt

    def status(self) -> CopilotConnectionStatusV1:
        if not self._receipts:
            return CopilotConnectionStatusV1(
                state="available",
                project_count=len(self._projects),
                delivery_enabled=False,
                status_summary="Ready to connect after reviewing the local Copilot CLI hook.",
            )
        current = self._receipts[-1]
        hook_current = self._hook_files.receipt_is_current(
            current.hook_file_receipt.receipt_id,
            helper_path=self._helper_path,
        )
        projects_current = current.projects == self._projects
        if current.operation == "disconnect" and hook_current:
            return CopilotConnectionStatusV1(
                state="available",
                project_count=len(self._projects),
                delivery_enabled=False,
                current_connection_digest=current.content_digest,
                status_summary="Copilot CLI is disconnected from Temper.",
            )
        now = self._now()
        valid = (
            current.operation == "connect"
            and hook_current
            and projects_current
            and current.consent.issued_at <= now < current.expires_at
        )
        return CopilotConnectionStatusV1(
            state="connected" if valid else "attention",
            project_count=len(current.projects),
            delivery_enabled=valid,
            expires_at=current.expires_at,
            current_connection_digest=current.content_digest,
            status_summary=(
                "Connected for approved delivery in registered Copilot CLI projects."
                if valid
                else "The Copilot connection no longer matches its signed local state."
            ),
        )

    def authorization(
        self, project_id: str, *, effective_at: datetime
    ) -> CopilotHookAuthorizationV1 | None:
        status = self.status()
        if status.state != "connected":
            return None
        current = self._receipts[-1]
        if not current.consent.issued_at <= effective_at < current.expires_at:
            return None
        project = next((item for item in current.projects if item.project_id == project_id), None)
        if project is None:
            return None
        return CopilotHookAuthorizationV1(
            subject_id=current.subject_id,
            project_id=project.project_id,
            consent_digest=canonical_digest(current.consent),
            project_registration_digest=project.project_registration_digest,
            delivery_enabled=current.delivery_enabled,
            effective_at=current.consent.issued_at,
            expires_at=current.expires_at,
        )

    def _issue_consent(
        self,
        issued_at: datetime,
        projects: tuple[CopilotConnectionProjectV1, ...],
    ) -> ConsentReceipt:
        project_ids = tuple(item.project_id for item in projects)
        return sign_consent(
            {
                "receipt_id": f"copilot-consent-{secrets.token_hex(12)}",
                "subject_id": self._subject_id,
                "source_selector": SourceSelector(
                    source_system="copilot_cli_hook",
                    selection_method="registered_projects_prospective",
                    source_ids=project_ids,
                ).model_dump(mode="json"),
                "scope": Scope(
                    subject_ids=(self._subject_id,),
                    project_ids=project_ids,
                    target_families=("copilot-cli",),
                    valid_from=issued_at,
                    valid_until=issued_at + _CONSENT_WINDOW,
                ).model_dump(mode="json"),
                "permitted_uses": [PermittedUse.AUDIT.value, PermittedUse.TARGET_DELIVERY.value],
                "issued_at": issued_at.isoformat(),
                "expires_at": (issued_at + _CONSENT_WINDOW).isoformat(),
                "retention_until": (issued_at + _CONSENT_WINDOW).isoformat(),
                "policy_version": "1.0.0",
            },
            self._signer,
        )

    @property
    def _path(self) -> Path:
        return self._state_root / "copilot-delivery" / "connection-receipts.json"

    def _append(
        self, receipt: CopilotConnectionReceiptV1, idempotency_key: str, fingerprint: str
    ) -> None:
        value = self._read()
        entries = value["entries"]
        if not isinstance(entries, list):
            raise CopilotConnectionError("Copilot connection index is invalid")
        entries.append(
            {
                "idempotency_key": idempotency_key,
                "receipt": receipt.model_dump(mode="json"),
                "request_fingerprint": fingerprint,
            }
        )
        _atomic_replace(self._path, (canonical_json(value) + "\n").encode())

    def _load(self) -> None:
        if not self._path.exists():
            return
        value = self._read()
        entries = value["entries"]
        if not isinstance(entries, list):
            raise CopilotConnectionError("Copilot connection index is invalid")
        previous_digest: Sha256Digest | None = None
        loaded: list[tuple[CopilotConnectionReceiptV1, str, str]] = []
        for raw in entries:
            try:
                if not isinstance(raw, dict):
                    raise ValueError
                receipt = CopilotConnectionReceiptV1.model_validate_json(
                    canonical_json(raw["receipt"]), strict=True
                )
                if (
                    receipt.subject_id != self._subject_id
                    or receipt.previous_connection_digest != previous_digest
                ):
                    raise ValueError
                verify_signed_governance(receipt.consent, self._identity)
                hook_receipt = self._hook_files.verified_receipt(
                    receipt.hook_file_receipt.receipt_id
                )
                if hook_receipt != receipt.hook_file_receipt:
                    raise ValueError
                public_key = base64.b64encode(
                    self._signer.private_key.public_key().public_bytes_raw()
                ).decode("ascii")
                verify_detached_envelope(
                    receipt.unsigned_payload,
                    receipt.signature,
                    public_key_base64=public_key,
                    expected_purpose="copilot_connection_change",
                )
                key = str(raw["idempotency_key"])
                fingerprint = str(raw["request_fingerprint"])
            except (KeyError, OSError, TypeError, ValueError) as error:
                raise CopilotConnectionError(
                    "Copilot connection index failed verification"
                ) from error
            loaded.append((receipt, key, fingerprint))
            previous_digest = receipt.content_digest
        for receipt, key, fingerprint in loaded:
            self._receipts.append(receipt)
            self._idempotency[key] = (fingerprint, receipt)

    def _read(self) -> dict[str, object]:
        if not self._path.exists():
            return {"entries": [], "version": 1}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CopilotConnectionError("Copilot connection index is invalid") from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise CopilotConnectionError("Copilot connection index is invalid")
        return value


def _disconnect_consent(current: CopilotConnectionReceiptV1 | None) -> ConsentReceipt:
    if current is None or current.operation != "connect":
        raise CopilotConnectionError("Copilot is not connected")
    return current.consent


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
