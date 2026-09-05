"""No-model Claude Code hook broker with signed cached projection validation."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from adaptation_compiler_lab.claude_delivery.models import (
    ClaudeHookAuditReceiptV1,
    ClaudeHookDisposition,
    ClaudeHookEvent,
    ClaudeHookInvocationV1,
    ClaudeHookProjectV1,
    ClaudeHookResultV1,
    ClaudeHookSpecificOutputV1,
    ClaudeProjectionLeaseV1,
    ClaudeUserPromptHookOutputV1,
)
from adaptation_compiler_lab.governance import SignerIdentity
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    SignatureVerificationError,
    verify_detached_envelope,
)
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.base import sha256_text


class ClaudeHookRuntimePort(Protocol):
    """Narrow local runtime seam; implementations may never call a model from these methods."""

    def project_for_directory(self, directory: Path) -> ClaudeHookProjectV1 | None: ...

    def projection_for_project(self, project_id: str) -> ClaudeProjectionLeaseV1 | None: ...

    def capture_user_prompt(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        prompt: str,
        observed_at: datetime,
    ) -> None: ...

    def capture_assistant_outcome(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        message: str,
        observed_at: datetime,
    ) -> None: ...

    def capture_failure(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        failure_class: str,
        failure_details: str | None,
        observed_at: datetime,
    ) -> None: ...

    def close_session(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        reason: str,
        observed_at: datetime,
    ) -> None: ...

    def append_audit(self, receipt: ClaudeHookAuditReceiptV1) -> None: ...


def parse_claude_hook_input(payload: Mapping[str, Any]) -> ClaudeHookInvocationV1:
    """Allowlist official fields and deliberately discard ``transcript_path`` and extras."""

    event = ClaudeHookEvent(_required_string(payload, "hook_event_name"))
    common: dict[str, object] = {
        "event": event,
        "session_id": _required_string(payload, "session_id"),
        "working_directory": _required_string(payload, "cwd"),
    }
    permission_mode = payload.get("permission_mode")
    if permission_mode is not None:
        common["permission_mode"] = _bounded_string(permission_mode, "permission_mode")
    if event is ClaudeHookEvent.USER_PROMPT_SUBMIT:
        common["prompt"] = _required_string(payload, "prompt")
    elif event is ClaudeHookEvent.STOP:
        common["last_assistant_message"] = _required_string(payload, "last_assistant_message")
    elif event is ClaudeHookEvent.STOP_FAILURE:
        common["failure_class"] = _required_string(payload, "error")
        if payload.get("error_details") is not None:
            common["failure_details"] = _bounded_string(payload["error_details"], "error_details")
        if payload.get("last_assistant_message") is not None:
            common["last_assistant_message"] = _bounded_string(
                payload["last_assistant_message"], "last_assistant_message"
            )
    else:
        common["session_end_reason"] = _required_string(payload, "reason")
    return ClaudeHookInvocationV1.model_validate(common, strict=True)


def issue_claude_projection_lease(
    *,
    lease_id: str,
    subject_id: str,
    project_id: str,
    instruction_environment_digest: str,
    external_release_digest: str,
    projection_digest: str,
    projection_manifest_digest: str,
    material: str,
    issued_at: datetime,
    expires_at: datetime,
    signer: GovernanceSigner,
) -> ClaudeProjectionLeaseV1:
    """Create one signed cached projection without invoking a target or provider."""

    placeholder = signer.envelope({}, purpose="claude_projection_lease", signed_at=issued_at)
    draft = ClaudeProjectionLeaseV1(
        lease_id=lease_id,
        subject_id=subject_id,
        project_id=project_id,
        instruction_environment_digest=instruction_environment_digest,
        external_release_digest=external_release_digest,
        projection_digest=projection_digest,
        projection_manifest_digest=projection_manifest_digest,
        material=material,
        material_digest=sha256_text(material),
        material_utf8_bytes=len(material.encode("utf-8")),
        issued_at=issued_at,
        expires_at=expires_at,
        signature=placeholder,
    )
    return draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose="claude_projection_lease",
                signed_at=issued_at,
            )
        }
    )


def verify_claude_projection_lease(
    lease: ClaudeProjectionLeaseV1,
    identity: SignerIdentity,
    *,
    project: ClaudeHookProjectV1,
    effective_at: datetime,
) -> None:
    """Verify signature, owner, project, native environment, and expiry."""

    if (
        lease.subject_id != identity.subject_id
        or lease.subject_id != project.subject_id
        or lease.project_id != project.project_id
    ):
        raise SignatureVerificationError("Claude projection crossed its owner or project")
    if lease.instruction_environment_digest != project.instruction_environment_digest:
        raise SignatureVerificationError("Claude projection instruction environment changed")
    if not lease.issued_at <= effective_at < lease.expires_at:
        raise SignatureVerificationError("Claude projection lease is not currently valid")
    if (
        lease.signature.signer_identity_id != identity.identity_id
        or lease.signature.key_fingerprint != identity.key_fingerprint
    ):
        raise SignatureVerificationError("Claude projection signer binding changed")
    verify_detached_envelope(
        lease.unsigned_payload,
        lease.signature,
        public_key_base64=identity.public_key_base64,
        expected_purpose="claude_projection_lease",
    )


class ClaudeHookBroker:
    """Dispatch official hook events while failing open to a silent, non-blocking no-op."""

    def __init__(
        self,
        port: ClaudeHookRuntimePort,
        *,
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
    ) -> None:
        if signer.subject_id != signer_identity.subject_id:
            raise ValueError("Claude hook signer crossed its configured subject")
        self._port = port
        self._signer = signer
        self._identity = signer_identity

    def handle(
        self,
        invocation: ClaudeHookInvocationV1,
        *,
        observed_at: datetime,
    ) -> ClaudeHookResultV1:
        """Handle one input without reading its transcript path or calling a model."""

        try:
            directory = Path(invocation.working_directory).expanduser().resolve(strict=False)
            project = self._port.project_for_directory(directory)
        except (OSError, ValueError):
            return self._silent(invocation, ClaudeHookDisposition.NOOP_UNREGISTERED)
        if project is None or project.subject_id != self._identity.subject_id:
            return self._silent(invocation, ClaudeHookDisposition.NOOP_UNREGISTERED)
        if not project.consent_current:
            return self._record(
                invocation,
                project,
                ClaudeHookDisposition.NOOP_UNAUTHORIZED,
                observed_at=observed_at,
            )
        if invocation.event is ClaudeHookEvent.USER_PROMPT_SUBMIT:
            return self._user_prompt(invocation, project, observed_at=observed_at)
        session_digest = sha256_text(invocation.session_id)
        if invocation.event is ClaudeHookEvent.STOP:
            if not project.learning_enabled:
                return self._record(
                    invocation,
                    project,
                    ClaudeHookDisposition.NOOP_UNAUTHORIZED,
                    observed_at=observed_at,
                )
            try:
                self._port.capture_assistant_outcome(
                    project=project,
                    session_digest=session_digest,
                    message=invocation.last_assistant_message or "",
                    observed_at=observed_at,
                )
            except (OSError, ValueError):
                return self._record(
                    invocation,
                    project,
                    ClaudeHookDisposition.NOOP_UNAUTHORIZED,
                    observed_at=observed_at,
                )
            return self._record(
                invocation,
                project,
                ClaudeHookDisposition.OUTCOME_CAPTURED,
                content_digest=sha256_text(invocation.last_assistant_message or ""),
                observed_at=observed_at,
            )
        if invocation.event is ClaudeHookEvent.STOP_FAILURE:
            if not project.learning_enabled:
                return self._record(
                    invocation,
                    project,
                    ClaudeHookDisposition.NOOP_UNAUTHORIZED,
                    observed_at=observed_at,
                )
            try:
                self._port.capture_failure(
                    project=project,
                    session_digest=session_digest,
                    failure_class=invocation.failure_class or "unknown",
                    failure_details=invocation.failure_details,
                    observed_at=observed_at,
                )
            except (OSError, ValueError):
                return self._record(
                    invocation,
                    project,
                    ClaudeHookDisposition.NOOP_UNAUTHORIZED,
                    observed_at=observed_at,
                )
            return self._record(
                invocation,
                project,
                ClaudeHookDisposition.FAILURE_CAPTURED,
                content_digest=sha256_text(invocation.failure_class or "unknown"),
                observed_at=observed_at,
            )
        try:
            self._port.close_session(
                project=project,
                session_digest=session_digest,
                reason=invocation.session_end_reason or "other",
                observed_at=observed_at,
            )
        except (OSError, ValueError):
            return self._record(
                invocation,
                project,
                ClaudeHookDisposition.NOOP_UNAUTHORIZED,
                observed_at=observed_at,
            )
        return self._record(
            invocation,
            project,
            ClaudeHookDisposition.SESSION_CLOSED,
            observed_at=observed_at,
        )

    def _user_prompt(
        self,
        invocation: ClaudeHookInvocationV1,
        project: ClaudeHookProjectV1,
        *,
        observed_at: datetime,
    ) -> ClaudeHookResultV1:
        prompt = invocation.prompt or ""
        session_digest = sha256_text(invocation.session_id)
        if project.learning_enabled:
            with suppress(OSError, ValueError):
                self._port.capture_user_prompt(
                    project=project,
                    session_digest=session_digest,
                    prompt=prompt,
                    observed_at=observed_at,
                )
        if not project.delivery_enabled:
            return self._record(
                invocation,
                project,
                ClaudeHookDisposition.NOOP_UNAUTHORIZED,
                content_digest=sha256_text(prompt),
                observed_at=observed_at,
            )
        try:
            lease = self._port.projection_for_project(project.project_id)
        except (OSError, ValueError):
            lease = None
        if lease is None:
            return self._record(
                invocation,
                project,
                ClaudeHookDisposition.NOOP_NO_PROJECTION,
                content_digest=sha256_text(prompt),
                observed_at=observed_at,
            )
        try:
            verify_claude_projection_lease(
                lease,
                self._identity,
                project=project,
                effective_at=observed_at,
            )
        except (SignatureVerificationError, ValueError):
            return self._record(
                invocation,
                project,
                ClaudeHookDisposition.NOOP_INVALID_PROJECTION,
                content_digest=sha256_text(prompt),
                observed_at=observed_at,
            )
        output = ClaudeUserPromptHookOutputV1(
            hook_specific_output=ClaudeHookSpecificOutputV1(additional_context=lease.material)
        )
        return self._record(
            invocation,
            project,
            ClaudeHookDisposition.DELIVERED,
            content_digest=sha256_text(prompt),
            projection_lease_digest=lease.content_digest,
            output=output,
            observed_at=observed_at,
        )

    def _silent(
        self,
        invocation: ClaudeHookInvocationV1,
        disposition: ClaudeHookDisposition,
    ) -> ClaudeHookResultV1:
        return ClaudeHookResultV1(event=invocation.event, disposition=disposition)

    def _record(
        self,
        invocation: ClaudeHookInvocationV1,
        project: ClaudeHookProjectV1,
        disposition: ClaudeHookDisposition,
        *,
        observed_at: datetime,
        content_digest: str | None = None,
        projection_lease_digest: str | None = None,
        output: ClaudeUserPromptHookOutputV1 | None = None,
    ) -> ClaudeHookResultV1:
        receipt_id = f"claude-hook-{secrets.token_hex(12)}"
        placeholder = self._signer.envelope(
            {},
            purpose="claude_hook_audit",
            signed_at=observed_at,
        )
        draft = ClaudeHookAuditReceiptV1(
            receipt_id=receipt_id,
            subject_id=project.subject_id,
            project_id=project.project_id,
            event=invocation.event,
            disposition=disposition,
            session_digest=sha256_text(invocation.session_id),
            invocation_digest=canonical_digest(invocation),
            content_digest=content_digest,
            projection_lease_digest=projection_lease_digest,
            occurred_at=observed_at,
            signature=placeholder,
        )
        receipt = draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="claude_hook_audit",
                    signed_at=observed_at,
                )
            }
        )
        self._port.append_audit(receipt)
        return ClaudeHookResultV1(
            event=invocation.event,
            disposition=disposition,
            audit_receipt=receipt,
            output=output,
        )


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    if field not in payload:
        raise ValueError(f"Claude hook input is missing {field}")
    return _bounded_string(payload[field], field)


def _bounded_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Claude hook {field} must be a non-empty string")
    return value
