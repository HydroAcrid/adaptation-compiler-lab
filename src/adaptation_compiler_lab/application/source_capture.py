"""Consent-bound capture of one exact completed source task.

The service deliberately stops at an encrypted raw envelope plus a signed capture receipt.
Message-level authority classification, Evidence construction, and lesson authoring remain
separate human-reviewed operations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adaptation_compiler_lab.connectors.models import SourceTaskSummary, SourceTurnDescriptor
from adaptation_compiler_lab.connectors.ports import SourceConnector
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import PermittedUse
from adaptation_compiler_lab.governance import (
    CaptureReceipt,
    ConsentReceipt,
    GovernanceObjectKind,
    SignerIdentity,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    governance_ref,
    sign_capture,
)
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore

PILOT_PERMITTED_USES = (
    PermittedUse.AUDIT,
    PermittedUse.BENCHMARK,
    PermittedUse.CONSTRUCTION,
    PermittedUse.DEVELOPMENT_EVALUATION,
    PermittedUse.PROMOTION,
    PermittedUse.TARGET_DELIVERY,
)
MINIMUM_SOURCE_QUIESCENCE = timedelta(minutes=15)
MAXIMUM_INVENTORY_PAGES = 100


class SourceCaptureError(ValueError):
    """A source payload cannot cross the consent and encryption boundary."""


class SourceCaptureRequest(FrozenModel):
    """Explicit request for one consented task and one immutable receipt identity."""

    task_id: Identifier
    consent_receipt_id: Identifier
    capture_receipt_id: Identifier
    captured_at: UtcDateTime


class SourceCaptureResult(FrozenModel):
    """Payload-free result returned after encrypted capture."""

    task_id: Identifier
    source_version: NonEmptyStr
    source_schema_digest: Sha256Digest
    payload_digest: Sha256Digest
    payload_size_bytes: int
    encrypted_locator: NonEmptyStr
    turns: tuple[SourceTurnDescriptor, ...]
    capture_receipt: CaptureReceipt


class SourceCaptureService:
    """Read exactly one authorized task and atomically bind its encrypted bytes."""

    def __init__(
        self,
        *,
        connector: SourceConnector,
        raw_store: LocalRawPayloadStore,
        governance_ledger: GovernanceLedger,
        signer: GovernanceSigner,
        identity: SignerIdentity,
        subject_id: str,
    ) -> None:
        if not subject_id:
            raise SourceCaptureError("source capture requires a subject")
        if not raw_store.encrypted:
            raise SourceCaptureError("source capture requires AES-256-GCM raw storage")
        if identity.subject_id != subject_id or signer.subject_id != subject_id:
            raise SourceCaptureError("source capture crossed the configured subject boundary")
        if signer.identity_id != identity.identity_id:
            raise SourceCaptureError("source capture signer does not match the identity")
        if signer.fingerprint != identity.key_fingerprint:
            raise SourceCaptureError("source capture signer key does not match the identity")
        if SignerRole.CONSENT not in identity.roles:
            raise SourceCaptureError("source capture identity lacks the consent role")
        self._connector = connector
        self._raw_store = raw_store
        self._ledger = governance_ledger
        self._signer = signer
        self._identity = identity
        self._subject_id = subject_id

    def capture(self, request: SourceCaptureRequest) -> SourceCaptureResult:
        """Capture only after all metadata checks pass; never infer a wider selector."""

        consent_value = self._ledger.get(
            GovernanceObjectKind.CONSENT_RECEIPT,
            request.consent_receipt_id,
        )
        if not isinstance(consent_value, ConsentReceipt):
            raise SourceCaptureError("referenced consent receipt is unavailable")
        consent = consent_value
        if consent.subject_id != self._subject_id:
            raise SourceCaptureError("consent subject does not match the source workspace")
        if consent.signature.signer_identity_id != self._identity.identity_id:
            raise SourceCaptureError("consent was not signed by the configured identity")
        if consent.source_selector.source_system != "codex_app_server":
            raise SourceCaptureError("source capture requires a Codex app-server selector")
        if consent.source_selector.selection_method != "explicit_task_ids":
            raise SourceCaptureError("source capture requires explicit task IDs")
        if consent.source_selector.source_ids != (request.task_id,):
            raise SourceCaptureError("consent must name exactly the requested task ID")
        if consent.permitted_uses != PILOT_PERMITTED_USES:
            raise SourceCaptureError("consent does not cover the complete frozen pilot use set")
        if request.captured_at < consent.issued_at or request.captured_at >= consent.expires_at:
            raise SourceCaptureError("capture time is outside the consent validity window")
        if request.captured_at > consent.retention_until:
            raise SourceCaptureError("capture time is after the retention deadline")
        if (
            self._identity.expires_at is not None
            and request.captured_at >= self._identity.expires_at
        ):
            raise SourceCaptureError("capture signer identity is expired")
        if (
            self._ledger.get(
                GovernanceObjectKind.CAPTURE_RECEIPT,
                request.capture_receipt_id,
            )
            is not None
        ):
            raise SourceCaptureError("capture receipt identity is already in use")

        summary = self._find_inventory_task(request.task_id)
        updated_at = datetime.fromtimestamp(
            summary.updated_at_epoch_seconds,
            tz=UTC,
        )
        if request.captured_at - updated_at < MINIMUM_SOURCE_QUIESCENCE:
            raise SourceCaptureError(
                "source task has not met the 15-minute completion quiescence window"
            )
        snapshot = self._connector.read_completed_task(request.task_id)
        reference = self._raw_store.reference_for(
            snapshot.raw_payload,
            media_type="application/vnd.openai.codex-thread+json",
        )
        expected_digest = f"sha256:{reference.sha256}"
        if expected_digest != snapshot.payload_digest:
            raise SourceCaptureError("source and raw-store payload digests disagree")
        receipt = sign_capture(
            {
                "receipt_id": request.capture_receipt_id,
                "subject_id": self._subject_id,
                "consent_ref": governance_ref(consent).model_dump(mode="json"),
                "source_selector": consent.source_selector.model_dump(mode="json"),
                "source_version": snapshot.source_version,
                "source_schema_digest": snapshot.source_schema_digest,
                "payload_digest": snapshot.payload_digest,
                "captured_at": request.captured_at.isoformat(),
                "synthetic": False,
            },
            self._signer,
        )

        existed = self._raw_store.contains(reference)
        stored = self._raw_store.put(
            snapshot.raw_payload,
            media_type=reference.media_type,
        )
        try:
            self._ledger.add(receipt)
        except BaseException:
            if not existed:
                self._raw_store.discard(stored)
            raise
        return SourceCaptureResult(
            task_id=request.task_id,
            source_version=snapshot.source_version,
            source_schema_digest=snapshot.source_schema_digest,
            payload_digest=snapshot.payload_digest,
            payload_size_bytes=reference.size_bytes,
            encrypted_locator=reference.relative_path,
            turns=snapshot.turns,
            capture_receipt=receipt,
        )

    def _find_inventory_task(self, task_id: str) -> SourceTaskSummary:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(MAXIMUM_INVENTORY_PAGES):
            page = self._connector.list_completed_tasks(cursor=cursor, limit=1000)
            matches = tuple(item for item in page.tasks if item.task_id == task_id)
            if len(matches) > 1:
                raise SourceCaptureError("source inventory returned a duplicate task ID")
            if matches:
                return matches[0]
            cursor = page.next_cursor
            if cursor is None:
                raise SourceCaptureError("consented task is absent from completed source inventory")
            if cursor in seen_cursors:
                raise SourceCaptureError("source inventory pagination cursor repeated")
            seen_cursors.add(cursor)
        raise SourceCaptureError("source inventory exceeded the bounded pagination limit")
