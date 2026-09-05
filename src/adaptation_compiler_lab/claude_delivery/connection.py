"""Signed, previewed Claude connection lifecycle over exact user-hook settings."""

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

from adaptation_compiler_lab.claude_delivery.models import (
    ClaudeConnectionPreviewV1,
    ClaudeConnectionProjectV1,
    ClaudeConnectionReceiptV1,
    ClaudeConnectionStatusV1,
    ClaudeHookAuthorizationV1,
)
from adaptation_compiler_lab.claude_delivery.settings import (
    ClaudeHookSettingsError,
    ClaudeHookSettingsService,
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


class ClaudeConnectionError(ValueError):
    """Raised when Claude cannot be connected or disconnected exactly."""


@dataclass(frozen=True, slots=True)
class _HeldPreview:
    preview: ClaudeConnectionPreviewV1
    projects: tuple[ClaudeConnectionProjectV1, ...]


class ClaudeConnectionService:
    """Bind explicit consent, registered projects, helper bytes, and hook settings."""

    def __init__(
        self,
        *,
        subject_id: str,
        projects: Mapping[str, Sha256Digest],
        settings: ClaudeHookSettingsService,
        settings_path: Path,
        helper_path: Path,
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
        state_root: Path,
        now: Callable[[], datetime],
    ) -> None:
        if not projects:
            raise ClaudeConnectionError("Claude requires at least one registered project")
        self._subject_id = subject_id
        self._projects = tuple(
            ClaudeConnectionProjectV1(
                project_id=project_id,
                project_registration_digest=digest,
            )
            for project_id, digest in sorted(projects.items())
        )
        self._settings = settings
        self._settings_path = settings_path.expanduser().resolve(strict=False)
        self._helper_path = helper_path.expanduser().resolve(strict=False)
        self._signer = signer
        self._identity = signer_identity
        self._state_root = state_root.expanduser().resolve()
        self._now = now
        self._previews: dict[str, _HeldPreview] = {}
        self._receipts: list[ClaudeConnectionReceiptV1] = []
        self._idempotency: dict[str, tuple[Sha256Digest, ClaudeConnectionReceiptV1]] = {}
        self._load()

    def preview(self, *, operation: Literal["connect", "disconnect"]) -> ClaudeConnectionPreviewV1:
        """Preview the exact connection transition without authenticating or calling Claude."""

        if operation not in {"connect", "disconnect"}:
            raise ClaudeConnectionError("unsupported Claude connection operation")
        current = self._receipts[-1] if self._receipts else None
        if operation == "connect" and current is not None and current.operation == "connect":
            raise ClaudeConnectionError("Claude is already connected")
        if operation == "disconnect" and (current is None or current.operation != "connect"):
            raise ClaudeConnectionError("Claude is not connected")
        try:
            settings = self._settings.preview(
                operation="install" if operation == "connect" else "uninstall",
                settings_path=self._settings_path,
                helper_path=self._helper_path,
            )
        except (OSError, ClaudeHookSettingsError) as error:
            raise ClaudeConnectionError("Claude hook settings are unavailable") from error
        now = self._now()
        consent = current.consent if operation == "disconnect" and current is not None else None
        expires_at = consent.expires_at if consent is not None else now + _CONSENT_WINDOW
        retention_until = consent.retention_until if consent is not None else now + _CONSENT_WINDOW
        preview = ClaudeConnectionPreviewV1(
            operation=operation,
            settings=settings,
            project_ids=tuple(item.project_id for item in self._projects),
            current_connection_digest=(None if current is None else current.content_digest),
            consent_expires_at=expires_at,
            retention_until=retention_until,
            learning_enabled=operation == "connect",
            delivery_enabled=operation == "connect",
        )
        self._previews[settings.preview_token] = _HeldPreview(
            preview=preview,
            projects=self._projects,
        )
        return preview

    def apply(
        self,
        *,
        preview_token: str,
        expected_before_digest: Sha256Digest,
        consent_confirmed: bool,
        idempotency_key: str,
    ) -> ClaudeConnectionReceiptV1:
        """Apply one exact preview and persist a signed connection transition."""

        fingerprint = canonical_digest(
            {
                "action": "apply_claude_connection",
                "consent_confirmed": consent_confirmed,
                "expected_before_digest": expected_before_digest,
                "preview_token": preview_token,
            }
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        if not consent_confirmed:
            raise ClaudeConnectionError("explicit Claude connection consent is required")
        held = self._previews.get(preview_token)
        if held is None:
            raise ClaudeConnectionError("Claude connection preview expired")
        preview = held.preview
        if preview.settings.before_digest != expected_before_digest:
            raise ClaudeConnectionError("Claude settings preview digest changed")
        current = self._receipts[-1] if self._receipts else None
        current_digest = None if current is None else current.content_digest
        if preview.current_connection_digest != current_digest:
            raise ClaudeConnectionError("Claude connection changed after preview")
        now = self._now()
        consent = (
            self._issue_consent(now, held.projects)
            if preview.operation == "connect"
            else self._disconnect_consent(current)
        )
        try:
            settings_receipt = self._settings.apply(
                preview_token=preview_token,
                expected_before_digest=expected_before_digest,
                idempotency_key=f"settings-{idempotency_key}",
            )
        except (OSError, ClaudeHookSettingsError) as error:
            raise ClaudeConnectionError("Claude settings change was refused") from error
        receipt = self._signed_receipt(
            operation=preview.operation,
            projects=held.projects,
            consent=consent,
            settings_receipt=settings_receipt,
            previous=current_digest,
            occurred_at=now,
        )
        try:
            self._append(
                receipt,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except (OSError, TypeError, ValueError) as error:
            with suppress(OSError, ClaudeHookSettingsError):
                self._settings.rollback(
                    receipt_id=settings_receipt.receipt_id,
                    expected_current_digest=settings_receipt.after_digest,
                    idempotency_key=f"connection-recovery-{idempotency_key}",
                )
            raise ClaudeConnectionError(
                "Claude connection receipt could not be persisted"
            ) from error
        self._receipts.append(receipt)
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        return receipt

    def status(self) -> ClaudeConnectionStatusV1:
        """Return only verified raw-free connection state."""

        return self._status(self._now())

    def _status(self, effective_at: datetime) -> ClaudeConnectionStatusV1:

        if not self._receipts:
            return ClaudeConnectionStatusV1(
                state="available",
                project_count=len(self._projects),
                learning_enabled=False,
                delivery_enabled=False,
                status_summary="Ready to connect after you review the local hook change.",
            )
        current = self._receipts[-1]
        settings_current = self._settings.receipt_is_current(
            current.settings_receipt.receipt_id,
            helper_path=self._helper_path,
        )
        projects_current = current.projects == self._projects
        if current.operation == "disconnect" and settings_current:
            return ClaudeConnectionStatusV1(
                state="available",
                project_count=len(self._projects),
                learning_enabled=False,
                delivery_enabled=False,
                current_connection_digest=current.content_digest,
                status_summary="Claude Code is disconnected from Temper.",
            )
        valid = (
            current.operation == "connect"
            and settings_current
            and projects_current
            and current.consent.issued_at <= effective_at < current.expires_at
        )
        return ClaudeConnectionStatusV1(
            state="connected" if valid else "attention",
            project_count=len(current.projects),
            learning_enabled=valid and current.learning_enabled,
            delivery_enabled=valid and current.delivery_enabled,
            expires_at=current.expires_at,
            current_connection_digest=current.content_digest,
            status_summary=(
                "Connected for approved prospective work in registered projects."
                if valid
                else "The Claude connection no longer matches its signed local state."
            ),
        )

    def authorization(
        self, project_id: str, *, effective_at: datetime | None = None
    ) -> ClaudeHookAuthorizationV1 | None:
        """Resolve an exact runtime authorization only from current signed state."""

        status = self._status(effective_at or self._now())
        if status.state != "connected":
            return None
        current = self._receipts[-1]
        project = next((item for item in current.projects if item.project_id == project_id), None)
        if project is None:
            return None
        return ClaudeHookAuthorizationV1(
            subject_id=current.subject_id,
            project_id=project.project_id,
            consent_digest=canonical_digest(current.consent),
            project_registration_digest=project.project_registration_digest,
            learning_enabled=current.learning_enabled,
            delivery_enabled=current.delivery_enabled,
            effective_at=current.consent.issued_at,
            expires_at=current.expires_at,
            retention_until=current.retention_until,
        )

    def _issue_consent(
        self,
        issued_at: datetime,
        projects: tuple[ClaudeConnectionProjectV1, ...],
    ) -> ConsentReceipt:
        project_ids = tuple(item.project_id for item in projects)
        return sign_consent(
            {
                "receipt_id": f"claude-consent-{secrets.token_hex(12)}",
                "subject_id": self._subject_id,
                "source_selector": SourceSelector(
                    source_system="claude_code_hook",
                    selection_method="registered_projects_prospective",
                    source_ids=project_ids,
                ).model_dump(mode="json"),
                "scope": Scope(
                    subject_ids=(self._subject_id,),
                    project_ids=project_ids,
                    target_families=("claude-code",),
                    valid_from=issued_at,
                    valid_until=issued_at + _CONSENT_WINDOW,
                ).model_dump(mode="json"),
                "permitted_uses": [
                    PermittedUse.AUDIT.value,
                    PermittedUse.CONSTRUCTION.value,
                    PermittedUse.PROMOTION.value,
                    PermittedUse.TARGET_DELIVERY.value,
                ],
                "issued_at": issued_at.isoformat(),
                "expires_at": (issued_at + _CONSENT_WINDOW).isoformat(),
                "retention_until": (issued_at + _CONSENT_WINDOW).isoformat(),
                "policy_version": "1.0.0",
            },
            self._signer,
        )

    @staticmethod
    def _disconnect_consent(current: ClaudeConnectionReceiptV1 | None) -> ConsentReceipt:
        if current is None or current.operation != "connect":
            raise ClaudeConnectionError("Claude is not connected")
        return current.consent

    def _signed_receipt(
        self,
        *,
        operation: Literal["connect", "disconnect"],
        projects: tuple[ClaudeConnectionProjectV1, ...],
        consent: ConsentReceipt,
        settings_receipt: object,
        previous: Sha256Digest | None,
        occurred_at: datetime,
    ) -> ClaudeConnectionReceiptV1:
        from adaptation_compiler_lab.claude_delivery.models import (
            ClaudeHookSettingsChangeReceiptV1,
        )

        if not isinstance(settings_receipt, ClaudeHookSettingsChangeReceiptV1):
            raise ClaudeConnectionError("Claude settings receipt is invalid")
        placeholder = self._signer.envelope(
            {}, purpose="claude_connection_change", signed_at=occurred_at
        )
        draft = ClaudeConnectionReceiptV1(
            receipt_id=f"claude-connection-{secrets.token_hex(12)}",
            operation=operation,
            subject_id=self._subject_id,
            projects=projects,
            consent=consent,
            settings_receipt=settings_receipt,
            previous_connection_digest=previous,
            learning_enabled=operation == "connect",
            delivery_enabled=operation == "connect",
            occurred_at=occurred_at,
            expires_at=consent.expires_at,
            retention_until=consent.retention_until,
            signature=placeholder,
        )
        return draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="claude_connection_change",
                    signed_at=occurred_at,
                )
            }
        )

    @property
    def _path(self) -> Path:
        return self._state_root / "claude-delivery" / "connection-receipts.json"

    def _append(
        self,
        receipt: ClaudeConnectionReceiptV1,
        *,
        idempotency_key: str,
        request_fingerprint: Sha256Digest,
    ) -> None:
        value = self._read_index()
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise ClaudeConnectionError("Claude connection receipt index is invalid")
        entries.append(
            {
                "idempotency_key": idempotency_key,
                "receipt": receipt.model_dump(mode="json"),
                "request_fingerprint": request_fingerprint,
            }
        )
        _atomic_replace(self._path, (canonical_json(value) + "\n").encode("utf-8"))

    def _load(self) -> None:
        value = self._read_index()
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise ClaudeConnectionError("Claude connection receipt index is invalid")
        previous: Sha256Digest | None = None
        loaded: list[tuple[ClaudeConnectionReceiptV1, str, Sha256Digest]] = []
        public_key = base64.b64encode(
            self._signer.private_key.public_key().public_bytes_raw()
        ).decode("ascii")
        for raw in entries:
            try:
                if not isinstance(raw, dict):
                    raise ValueError
                receipt = ClaudeConnectionReceiptV1.model_validate_json(
                    canonical_json(raw["receipt"]), strict=True
                )
                idempotency_key = str(raw["idempotency_key"])
                fingerprint = str(raw["request_fingerprint"])
                if receipt.subject_id != self._subject_id:
                    raise ValueError
                if receipt.previous_connection_digest != previous:
                    raise ValueError
                verify_signed_governance(receipt.consent, self._identity)
                settings_receipt = self._settings.verified_receipt(
                    receipt.settings_receipt.receipt_id
                )
                if settings_receipt != receipt.settings_receipt:
                    raise ValueError
                verify_detached_envelope(
                    receipt.unsigned_payload,
                    receipt.signature,
                    public_key_base64=public_key,
                    expected_purpose="claude_connection_change",
                )
            except (KeyError, OSError, TypeError, ValueError) as error:
                raise ClaudeConnectionError(
                    "Claude connection receipt index failed verification"
                ) from error
            loaded.append((receipt, idempotency_key, fingerprint))
            previous = receipt.content_digest
        for receipt, idempotency_key, fingerprint in loaded:
            self._receipts.append(receipt)
            self._idempotency[idempotency_key] = (fingerprint, receipt)

    def _read_index(self) -> dict[str, object]:
        if not self._path.exists():
            return {"entries": [], "version": 1}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ClaudeConnectionError("Claude connection receipt index is invalid") from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ClaudeConnectionError("Claude connection receipt index is invalid")
        return value

    def _replay(
        self, idempotency_key: str, fingerprint: Sha256Digest
    ) -> ClaudeConnectionReceiptV1 | None:
        prior = self._idempotency.get(idempotency_key)
        if prior is None:
            return None
        if prior[0] != fingerprint:
            raise ClaudeConnectionError(
                "idempotency key was reused for another Claude connection change"
            )
        return prior[1]


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise
