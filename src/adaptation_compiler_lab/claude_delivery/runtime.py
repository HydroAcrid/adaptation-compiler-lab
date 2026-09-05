"""Governed local runtime behind the private Claude Code hook transport.

This module deliberately contains no semantic interpreter or provider client. Hook calls may
only resolve a registered project, rehash documented native instruction sources, persist
encrypted payload bytes, and return an already prepared signed projection lease.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Final, Literal

from adaptation_compiler_lab.claude_delivery.models import (
    ClaudeCapturedAuthority,
    ClaudeHookAuditReceiptV1,
    ClaudeHookAuthorizationV1,
    ClaudeHookCaptureReceiptV1,
    ClaudeHookEvent,
    ClaudeHookLedgerEntryV1,
    ClaudeHookProjectV1,
    ClaudeProjectionLeaseV1,
    ClaudeProjectionManifestV1,
)
from adaptation_compiler_lab.claude_delivery.projection import (
    build_claude_projection_manifest,
    render_claude_hook_projection,
)
from adaptation_compiler_lab.claude_delivery.service import (
    ClaudeHookBroker,
    issue_claude_projection_lease,
    parse_claude_hook_input,
)
from adaptation_compiler_lab.governance import SignerIdentity
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    SignatureVerificationError,
    verify_detached_envelope,
)
from adaptation_compiler_lab.instruction_environment.models import NativeTarget
from adaptation_compiler_lab.instruction_environment.resolver import (
    apply_instruction_environment,
    build_instruction_delta_plan,
)
from adaptation_compiler_lab.instruction_environment.service import InstructionEnvironmentService
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.runtime.models import CanonicalRuntimeProjection
from adaptation_compiler_lab.serialization import canonical_bytes, canonical_json
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind

_LEASE_TTL: Final = timedelta(minutes=5)
_MAX_CAPTURE_BYTES: Final = 1_048_576

ClaudeAuthorizationProvider = Callable[[str, datetime], ClaudeHookAuthorizationV1 | None]
ClaudeProjectionProvider = Callable[[str, datetime], CanonicalRuntimeProjection | None]


class ClaudeHookRuntimeError(ValueError):
    """The local Claude runtime refused an unsafe or incoherent operation."""


class ClaudeHookLedger:
    """Append-only signed and chained local index for raw-free Claude hook receipts."""

    def __init__(
        self,
        path: Path,
        *,
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
    ) -> None:
        if (
            signer.subject_id != signer_identity.subject_id
            or signer.identity_id != signer_identity.identity_id
            or signer.fingerprint != signer_identity.key_fingerprint
        ):
            raise ClaudeHookRuntimeError("Claude hook ledger signer binding changed")
        self._path = path.expanduser().resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._set_mode(self._path.parent, 0o700)
        self._signer = signer
        self._identity = signer_identity
        self._lock = Lock()
        self._entries = list(self._load())
        self._stat = self._file_stat()

    @property
    def entries(self) -> tuple[ClaudeHookLedgerEntryV1, ...]:
        return tuple(self._entries)

    def append_capture(
        self,
        receipt: ClaudeHookCaptureReceiptV1,
        raw_reference: RawPayloadRef,
        *,
        appended_at: datetime,
    ) -> ClaudeHookLedgerEntryV1:
        self._verify_capture_receipt(receipt)
        if (
            raw_reference.sha256 != receipt.raw_payload_sha256
            or raw_reference.size_bytes != receipt.raw_payload_size_bytes
            or raw_reference.media_type != receipt.media_type
        ):
            raise ClaudeHookRuntimeError("Claude capture raw reference binding changed")
        return self._append(
            entry_kind="capture",
            subject_id=receipt.subject_id,
            project_id=receipt.project_id,
            capture_receipt=receipt,
            audit_receipt=None,
            raw_payload_relative_path=raw_reference.relative_path,
            appended_at=appended_at,
        )

    def append_audit(
        self,
        receipt: ClaudeHookAuditReceiptV1,
    ) -> ClaudeHookLedgerEntryV1:
        self._verify_audit_receipt(receipt)
        return self._append(
            entry_kind="audit",
            subject_id=receipt.subject_id,
            project_id=receipt.project_id,
            capture_receipt=None,
            audit_receipt=receipt,
            raw_payload_relative_path=None,
            appended_at=receipt.occurred_at,
        )

    def _append(
        self,
        *,
        entry_kind: Literal["capture", "audit"],
        subject_id: str,
        project_id: str,
        capture_receipt: ClaudeHookCaptureReceiptV1 | None,
        audit_receipt: ClaudeHookAuditReceiptV1 | None,
        raw_payload_relative_path: str | None,
        appended_at: datetime,
    ) -> ClaudeHookLedgerEntryV1:
        if subject_id != self._identity.subject_id:
            raise ClaudeHookRuntimeError("Claude hook ledger crossed its subject boundary")
        with self._lock:
            if self._file_stat() != self._stat:
                raise ClaudeHookRuntimeError("Claude hook ledger changed outside this runtime")
            prior = self._entries[-1] if self._entries else None
            placeholder = self._signer.envelope(
                {}, purpose="claude_hook_ledger_entry", signed_at=appended_at
            )
            draft = ClaudeHookLedgerEntryV1(
                entry_id=f"claude-ledger-{secrets.token_hex(12)}",
                subject_id=subject_id,
                project_id=project_id,
                sequence=len(self._entries) + 1,
                previous_entry_digest=(None if prior is None else prior.content_digest),
                entry_kind=entry_kind,
                capture_receipt=capture_receipt,
                audit_receipt=audit_receipt,
                raw_payload_relative_path=raw_payload_relative_path,
                appended_at=appended_at,
                signature=placeholder,
            )
            entry = draft.model_copy(
                update={
                    "signature": self._signer.envelope(
                        draft.unsigned_payload,
                        purpose="claude_hook_ledger_entry",
                        signed_at=appended_at,
                    )
                }
            )
            encoded = (canonical_json(entry) + "\n").encode("utf-8")
            descriptor = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                with os.fdopen(descriptor, "ab") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                raise
            self._set_mode(self._path, 0o600)
            self._entries.append(entry)
            self._stat = self._file_stat()
            return entry

    def _load(self) -> tuple[ClaudeHookLedgerEntryV1, ...]:
        if not self._path.exists():
            return ()
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise ClaudeHookRuntimeError("Claude hook ledger is unreadable") from error
        entries: list[ClaudeHookLedgerEntryV1] = []
        for sequence, line in enumerate(lines, start=1):
            if not line:
                raise ClaudeHookRuntimeError("Claude hook ledger contains an empty entry")
            try:
                entry = ClaudeHookLedgerEntryV1.model_validate_json(line, strict=True)
                self._verify_entry(entry, sequence=sequence, prior=entries[-1] if entries else None)
            except (SignatureVerificationError, ValueError) as error:
                raise ClaudeHookRuntimeError("Claude hook ledger verification failed") from error
            entries.append(entry)
        return tuple(entries)

    def _verify_entry(
        self,
        entry: ClaudeHookLedgerEntryV1,
        *,
        sequence: int,
        prior: ClaudeHookLedgerEntryV1 | None,
    ) -> None:
        if (
            entry.subject_id != self._identity.subject_id
            or entry.sequence != sequence
            or entry.previous_entry_digest != (None if prior is None else prior.content_digest)
        ):
            raise ClaudeHookRuntimeError("Claude hook ledger chain verification failed")
        verify_detached_envelope(
            entry.unsigned_payload,
            entry.signature,
            public_key_base64=self._identity.public_key_base64,
            expected_purpose="claude_hook_ledger_entry",
        )
        if entry.capture_receipt is not None:
            self._verify_capture_receipt(entry.capture_receipt)
        if entry.audit_receipt is not None:
            self._verify_audit_receipt(entry.audit_receipt)

    def _verify_capture_receipt(self, receipt: ClaudeHookCaptureReceiptV1) -> None:
        if receipt.subject_id != self._identity.subject_id:
            raise ClaudeHookRuntimeError("Claude capture receipt crossed its subject")
        verify_detached_envelope(
            receipt.unsigned_payload,
            receipt.signature,
            public_key_base64=self._identity.public_key_base64,
            expected_purpose="claude_hook_capture",
        )

    def _verify_audit_receipt(self, receipt: ClaudeHookAuditReceiptV1) -> None:
        if receipt.subject_id != self._identity.subject_id:
            raise ClaudeHookRuntimeError("Claude audit receipt crossed its subject")
        verify_detached_envelope(
            receipt.unsigned_payload,
            receipt.signature,
            public_key_base64=self._identity.public_key_base64,
            expected_purpose="claude_hook_audit",
        )

    def _file_stat(self) -> tuple[int, int] | None:
        try:
            current = self._path.stat()
        except FileNotFoundError:
            return None
        return current.st_size, current.st_mtime_ns

    @staticmethod
    def _set_mode(path: Path, mode: int) -> None:
        with suppress(OSError):
            path.chmod(mode)


class LocalClaudeHookRuntimePort:
    """Consent-aware encrypted capture and signed in-memory projection cache."""

    def __init__(
        self,
        *,
        projects: Mapping[str, Path],
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
        raw_store: LocalRawPayloadStore,
        ledger: ClaudeHookLedger,
        instruction_environment: InstructionEnvironmentService,
        authorization_provider: ClaudeAuthorizationProvider,
        projection_provider: ClaudeProjectionProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not raw_store.encrypted:
            raise ClaudeHookRuntimeError("Claude hook capture requires encrypted raw storage")
        if (
            signer.subject_id != signer_identity.subject_id
            or signer.identity_id != signer_identity.identity_id
            or signer.fingerprint != signer_identity.key_fingerprint
        ):
            raise ClaudeHookRuntimeError("Claude hook runtime signer binding changed")
        resolved = {
            project_id: root.expanduser().resolve(strict=True)
            for project_id, root in projects.items()
        }
        pairs = tuple(resolved.items())
        for index, (project_id, root) in enumerate(pairs):
            if not root.is_dir():
                raise ClaudeHookRuntimeError("Claude hook project root is not a directory")
            for other_id, other_root in pairs[index + 1 :]:
                if (
                    root == other_root
                    or root.is_relative_to(other_root)
                    or other_root.is_relative_to(root)
                ):
                    raise ClaudeHookRuntimeError(
                        f"Claude hook projects overlap: {project_id} and {other_id}"
                    )
        self._projects = resolved
        self._signer = signer
        self._identity = signer_identity
        self._raw_store = raw_store
        self._ledger = ledger
        self._instruction_environment = instruction_environment
        self._authorization_provider = authorization_provider
        self._projection_provider = projection_provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._leases: dict[str, ClaudeProjectionLeaseV1] = {}
        self._manifests: dict[str, ClaudeProjectionManifestV1] = {}

    def project_for_directory(self, directory: Path) -> ClaudeHookProjectV1 | None:
        resolved = directory.expanduser().resolve(strict=True)
        if not resolved.is_dir():
            return None
        matches = tuple(
            (project_id, root)
            for project_id, root in self._projects.items()
            if resolved == root or resolved.is_relative_to(root)
        )
        if len(matches) != 1:
            return None
        project_id, _root = matches[0]
        environment = self._instruction_environment.refresh(
            project_id=project_id,
            target=NativeTarget.CLAUDE,
            working_directory=resolved,
        )
        now = self._clock()
        authorization = self._current_authorization(project_id, now)
        return ClaudeHookProjectV1(
            subject_id=self._identity.subject_id,
            project_id=project_id,
            instruction_environment_digest=environment.content_digest,
            consent_current=authorization is not None,
            learning_enabled=(authorization is not None and authorization.learning_enabled),
            delivery_enabled=(authorization is not None and authorization.delivery_enabled),
        )

    def prepare_projection(
        self,
        project_id: str,
        *,
        issued_at: datetime | None = None,
    ) -> ClaudeProjectionLeaseV1 | None:
        """Prepare a lease outside the hook path using only cached semantic relations."""

        now = issued_at or self._clock()
        authorization = self._current_authorization(project_id, now)
        if authorization is None or not authorization.delivery_enabled:
            return self._clear_projection(project_id)
        root = self._projects.get(project_id)
        if root is None:
            raise ClaudeHookRuntimeError("Claude projection names an unregistered project")
        environment = self._instruction_environment.refresh(
            project_id=project_id,
            target=NativeTarget.CLAUDE,
            working_directory=root,
        )
        if not environment.complete:
            return self._clear_projection(project_id)
        projection = self._projection_provider(project_id, now)
        if projection is None or not projection.clauses:
            return self._clear_projection(project_id)
        self._validate_projection(projection, project_id=project_id)
        relations = self._instruction_environment.cached_relations(projection, environment)
        delta_plan = build_instruction_delta_plan(
            projection,
            environment,
            semantic_relations=relations,
        )
        delta = apply_instruction_environment(projection, delta_plan)
        if not delta.clauses:
            return self._clear_projection(project_id)
        rendered = render_claude_hook_projection(delta)
        manifest = build_claude_projection_manifest(
            subject_id=self._identity.subject_id,
            projection=projection,
            delta_plan=delta_plan,
            rendered=rendered,
            created_at=now,
        )
        expires_at = min(authorization.expires_at, now + _LEASE_TTL)
        if expires_at <= now:
            return self._clear_projection(project_id)
        lease = issue_claude_projection_lease(
            lease_id=f"claude-projection-{project_id}-{secrets.token_hex(8)}",
            subject_id=self._identity.subject_id,
            project_id=project_id,
            instruction_environment_digest=environment.content_digest,
            external_release_digest=projection.external_release_digest,
            projection_digest=delta.content_digest,
            projection_manifest_digest=manifest.content_digest,
            material=rendered.content,
            issued_at=now,
            expires_at=expires_at,
            signer=self._signer,
        )
        self._leases[project_id] = lease
        self._manifests[project_id] = manifest
        return lease

    def prepare_all(
        self, *, issued_at: datetime | None = None
    ) -> tuple[ClaudeProjectionLeaseV1, ...]:
        leases = tuple(
            lease
            for project_id in sorted(self._projects)
            if (lease := self.prepare_projection(project_id, issued_at=issued_at)) is not None
        )
        return leases

    def projection_for_project(self, project_id: str) -> ClaudeProjectionLeaseV1 | None:
        return self._leases.get(project_id)

    def projection_manifest(self, project_id: str) -> ClaudeProjectionManifestV1 | None:
        return self._manifests.get(project_id)

    def capture_user_prompt(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        prompt: str,
        observed_at: datetime,
    ) -> None:
        self._capture(
            project=project,
            session_digest=session_digest,
            payload=prompt.encode("utf-8"),
            event=ClaudeHookEvent.USER_PROMPT_SUBMIT,
            authority=ClaudeCapturedAuthority.USER_AUTHORED_INPUT,
            media_type="text/plain; charset=utf-8; role=user",
            observed_at=observed_at,
        )

    def capture_assistant_outcome(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        message: str,
        observed_at: datetime,
    ) -> None:
        self._capture(
            project=project,
            session_digest=session_digest,
            payload=message.encode("utf-8"),
            event=ClaudeHookEvent.STOP,
            authority=ClaudeCapturedAuthority.UNTRUSTED_ASSISTANT_CONTEXT,
            media_type="text/plain; charset=utf-8; role=assistant",
            observed_at=observed_at,
        )

    def capture_failure(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        failure_class: str,
        failure_details: str | None,
        observed_at: datetime,
    ) -> None:
        payload = canonical_bytes(
            {
                "failure_class": failure_class,
                "failure_details": failure_details,
            }
        )
        self._capture(
            project=project,
            session_digest=session_digest,
            payload=payload,
            event=ClaudeHookEvent.STOP_FAILURE,
            authority=ClaudeCapturedAuthority.UNTRUSTED_FAILURE_CONTEXT,
            media_type="application/json; role=failure-context",
            observed_at=observed_at,
        )

    def close_session(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        reason: str,
        observed_at: datetime,
    ) -> None:
        del session_digest, reason
        self._require_learning_authorization(project, observed_at)

    def append_audit(self, receipt: ClaudeHookAuditReceiptV1) -> None:
        self._ledger.append_audit(receipt)

    def _capture(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        payload: bytes,
        event: Literal[
            ClaudeHookEvent.USER_PROMPT_SUBMIT,
            ClaudeHookEvent.STOP,
            ClaudeHookEvent.STOP_FAILURE,
        ],
        authority: ClaudeCapturedAuthority,
        media_type: str,
        observed_at: datetime,
    ) -> None:
        authorization = self._require_learning_authorization(project, observed_at)
        if not payload or len(payload) > _MAX_CAPTURE_BYTES:
            raise ClaudeHookRuntimeError("Claude hook payload is empty or oversized")
        prospective = self._raw_store.reference_for(payload, media_type=media_type)
        existed = self._raw_store.contains(prospective)
        reference = self._raw_store.put(payload, media_type=media_type)
        placeholder = self._signer.envelope(
            {}, purpose="claude_hook_capture", signed_at=observed_at
        )
        draft = ClaudeHookCaptureReceiptV1(
            receipt_id=f"claude-capture-{secrets.token_hex(12)}",
            subject_id=self._identity.subject_id,
            project_id=project.project_id,
            event=event,
            authority=authority,
            session_digest=session_digest,
            content_digest=f"sha256:{reference.sha256}",
            raw_payload_sha256=reference.sha256,
            raw_payload_size_bytes=reference.size_bytes,
            media_type=reference.media_type,
            consent_digest=authorization.consent_digest,
            project_registration_digest=authorization.project_registration_digest,
            captured_at=observed_at,
            retention_until=authorization.retention_until,
            signature=placeholder,
        )
        receipt = draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="claude_hook_capture",
                    signed_at=observed_at,
                )
            }
        )
        try:
            self._ledger.append_capture(receipt, reference, appended_at=observed_at)
        except BaseException:
            if not existed:
                self._raw_store.discard(reference)
            raise

    def _require_learning_authorization(
        self,
        project: ClaudeHookProjectV1,
        observed_at: datetime,
    ) -> ClaudeHookAuthorizationV1:
        if (
            project.subject_id != self._identity.subject_id
            or project.project_id not in self._projects
        ):
            raise ClaudeHookRuntimeError("Claude capture crossed its owner or project")
        authorization = self._current_authorization(project.project_id, observed_at)
        if authorization is None or not authorization.learning_enabled:
            raise ClaudeHookRuntimeError("Claude source learning is not authorized")
        return authorization

    def _current_authorization(
        self,
        project_id: str,
        effective_at: datetime,
    ) -> ClaudeHookAuthorizationV1 | None:
        if effective_at.tzinfo is None or effective_at.utcoffset() is None:
            raise ClaudeHookRuntimeError("Claude runtime time must be timezone-aware")
        authorization = self._authorization_provider(project_id, effective_at)
        if authorization is None:
            return None
        if (
            authorization.subject_id != self._identity.subject_id
            or authorization.project_id != project_id
        ):
            raise ClaudeHookRuntimeError("Claude runtime authorization binding is invalid")
        if (
            not authorization.effective_at <= effective_at < authorization.expires_at
            or authorization.retention_until <= effective_at
        ):
            return None
        return authorization

    def _validate_projection(
        self,
        projection: CanonicalRuntimeProjection,
        *,
        project_id: str,
    ) -> None:
        if (
            projection.context.subject_id != self._identity.subject_id
            or projection.context.project_id != project_id
            or projection.context.target_family != TargetKind.CLAUDE_CODE.value
            or ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        ):
            raise ClaudeHookRuntimeError("Claude projection context binding changed")

    def _clear_projection(self, project_id: str) -> ClaudeProjectionLeaseV1 | None:
        self._leases.pop(project_id, None)
        self._manifests.pop(project_id, None)
        return None


class ClaudeHookRuntimeHandler:
    """Callable protocol adapter that returns only official Claude hook output fields."""

    def __init__(
        self,
        port: LocalClaudeHookRuntimePort,
        *,
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.port = port
        self._clock = clock or (lambda: datetime.now(UTC))
        self._broker = ClaudeHookBroker(
            port,
            signer=signer,
            signer_identity=signer_identity,
        )

    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        invocation = parse_claude_hook_input(payload)
        result = self._broker.handle(invocation, observed_at=self._clock())
        if result.output is None:
            return None
        return result.output.claude_payload()
