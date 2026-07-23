"""Append-only SQLite persistence for signed governance objects."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from adaptation_compiler_lab.governance import (
    AdjudicationRecord,
    BenchmarkRegistration,
    CaptureReceipt,
    ConditionMaterialReceipt,
    ConsentReceipt,
    CustodyAccessEvent,
    CustodyManifest,
    DependencyImpact,
    GovernanceEvent,
    GovernanceObjectKind,
    InvalidationEvent,
    RecallReport,
    SignedGovernanceObject,
    SignerIdentity,
    TombstoneReceipt,
    TrialResult,
)
from adaptation_compiler_lab.governance.signing import verify_signed_governance
from adaptation_compiler_lab.persistence.errors import IntegrityError, RecordConflictError
from adaptation_compiler_lab.persistence.migrations import MigrationRunner
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_MODELS: dict[GovernanceObjectKind, type[SignedGovernanceObject]] = {
    GovernanceObjectKind.SIGNER_IDENTITY: SignerIdentity,
    GovernanceObjectKind.CONSENT_RECEIPT: ConsentReceipt,
    GovernanceObjectKind.CAPTURE_RECEIPT: CaptureReceipt,
    GovernanceObjectKind.GOVERNANCE_EVENT: GovernanceEvent,
    GovernanceObjectKind.DEPENDENCY_IMPACT: DependencyImpact,
    GovernanceObjectKind.INVALIDATION_EVENT: InvalidationEvent,
    GovernanceObjectKind.TOMBSTONE_RECEIPT: TombstoneReceipt,
    GovernanceObjectKind.RECALL_REPORT: RecallReport,
    GovernanceObjectKind.CUSTODY_MANIFEST: CustodyManifest,
    GovernanceObjectKind.BENCHMARK_REGISTRATION: BenchmarkRegistration,
    GovernanceObjectKind.CONDITION_MATERIAL_RECEIPT: ConditionMaterialReceipt,
    GovernanceObjectKind.TRIAL_RESULT: TrialResult,
    GovernanceObjectKind.ADJUDICATION_RECORD: AdjudicationRecord,
    GovernanceObjectKind.CUSTODY_ACCESS_EVENT: CustodyAccessEvent,
}


def _object_id(value: SignedGovernanceObject) -> str:
    if isinstance(value, SignerIdentity):
        return value.identity_id
    if isinstance(value, GovernanceEvent):
        return value.event_id
    if isinstance(value, DependencyImpact):
        return value.impact_id
    if isinstance(value, InvalidationEvent):
        return value.event_id
    if isinstance(value, RecallReport):
        return value.report_id
    if isinstance(value, CustodyManifest):
        return value.manifest_id
    if isinstance(value, BenchmarkRegistration):
        return value.registration_id
    if isinstance(value, TrialResult):
        return value.result_id
    if isinstance(value, AdjudicationRecord):
        return value.adjudication_id
    if isinstance(value, CustodyAccessEvent):
        return value.event_id
    return value.receipt_id


def _created_at(value: SignedGovernanceObject) -> str:
    if isinstance(value, SignerIdentity):
        return value.created_at.isoformat()
    if isinstance(value, ConsentReceipt):
        return value.issued_at.isoformat()
    if isinstance(value, CaptureReceipt):
        return value.captured_at.isoformat()
    if isinstance(value, GovernanceEvent):
        return value.occurred_at.isoformat()
    if isinstance(value, DependencyImpact):
        return value.generated_at.isoformat()
    if isinstance(value, InvalidationEvent):
        return value.effective_at.isoformat()
    if isinstance(value, TombstoneReceipt):
        return value.purged_at.isoformat()
    if isinstance(value, RecallReport):
        return value.completed_at.isoformat()
    if isinstance(value, CustodyManifest):
        return value.sealed_at.isoformat()
    if isinstance(value, BenchmarkRegistration):
        return value.registered_at.isoformat()
    if isinstance(value, ConditionMaterialReceipt):
        return value.frozen_at.isoformat()
    if isinstance(value, TrialResult):
        return value.scored_at.isoformat()
    if isinstance(value, AdjudicationRecord):
        return value.adjudicated_at.isoformat()
    return value.occurred_at.isoformat()


class GovernanceLedger:
    """Subject-scoped append-only store that verifies every object on write and read."""

    def __init__(self, database: Path, *, subject_id: str) -> None:
        if not subject_id:
            raise ValueError("subject_id must not be empty")
        self._database = database.expanduser().resolve()
        self._subject_id = subject_id

    def initialize(self) -> int:
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            return MigrationRunner().migrate(connection)

    def add(self, value: SignedGovernanceObject) -> bool:
        with self._connect() as connection:
            inserted = self.add_to_connection(connection, value)
            connection.commit()
        return inserted

    def add_to_connection(
        self,
        connection: sqlite3.Connection,
        value: SignedGovernanceObject,
    ) -> bool:
        """Append through an existing transaction without committing it."""

        if value.subject_id != self._subject_id:
            raise IntegrityError("governance object crossed the configured subject boundary")
        identity = (
            value
            if isinstance(value, SignerIdentity)
            else self._require_identity(connection, value.signature.signer_identity_id)
        )
        verify_signed_governance(value, identity)
        rendered = canonical_json(value)
        digest = canonical_digest(value).removeprefix("sha256:")
        object_id = _object_id(value)
        expires_at = (
            value.expires_at.isoformat()
            if isinstance(value, (SignerIdentity, ConsentReceipt)) and value.expires_at is not None
            else None
        )
        retention_until = (
            value.retention_until.isoformat() if isinstance(value, ConsentReceipt) else None
        )
        existing = connection.execute(
            """
            SELECT canonical_json FROM governance_objects
            WHERE governance_type = ? AND object_id = ?
            """,
            (value.governance_type.value, object_id),
        ).fetchone()
        if existing is not None:
            if str(existing[0]) == rendered:
                return False
            raise RecordConflictError("immutable governance identity already has different content")
        connection.execute(
            """
            INSERT INTO governance_objects (
                governance_type, object_id, schema_version, subject_id,
                signer_identity_id, key_fingerprint, canonicalization_version,
                canonical_json, content_sha256, signature_base64, created_at,
                expires_at, retention_until
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                value.governance_type.value,
                object_id,
                value.schema_version,
                value.subject_id,
                value.signature.signer_identity_id,
                value.signature.key_fingerprint,
                value.signature.canonicalization_version,
                rendered,
                digest,
                value.signature.signature_base64,
                _created_at(value),
                expires_at,
                retention_until,
            ),
        )
        return True

    def get(
        self, governance_type: GovernanceObjectKind, object_id: str
    ) -> SignedGovernanceObject | None:
        with self._connect() as connection:
            return self.get_from_connection(connection, governance_type, object_id)

    def get_from_connection(
        self,
        connection: sqlite3.Connection,
        governance_type: GovernanceObjectKind,
        object_id: str,
    ) -> SignedGovernanceObject | None:
        row = connection.execute(
            """
            SELECT * FROM governance_objects
            WHERE governance_type = ? AND object_id = ? AND subject_id = ?
            """,
            (governance_type.value, object_id, self._subject_id),
        ).fetchone()
        if row is None:
            return None
        return self._decode(row, connection)

    def require_identity(self, identity_id: str) -> SignerIdentity:
        with self._connect() as connection:
            return self._require_identity(connection, identity_id)

    def _require_identity(self, connection: sqlite3.Connection, identity_id: str) -> SignerIdentity:
        value = self.get_from_connection(
            connection, GovernanceObjectKind.SIGNER_IDENTITY, identity_id
        )
        if not isinstance(value, SignerIdentity):
            raise IntegrityError(f"signer identity is unavailable: {identity_id}")
        return value

    def list(self, governance_type: GovernanceObjectKind) -> tuple[SignedGovernanceObject, ...]:
        with self._connect() as connection:
            return self.list_from_connection(connection, governance_type)

    def list_from_connection(
        self,
        connection: sqlite3.Connection,
        governance_type: GovernanceObjectKind,
    ) -> tuple[SignedGovernanceObject, ...]:
        rows = connection.execute(
            """
            SELECT * FROM governance_objects
            WHERE governance_type = ? AND subject_id = ?
            ORDER BY created_at, object_id
            """,
            (governance_type.value, self._subject_id),
        ).fetchall()
        return tuple(self._decode(row, connection) for row in rows)

    def _decode(self, row: sqlite3.Row, connection: sqlite3.Connection) -> SignedGovernanceObject:
        try:
            kind = GovernanceObjectKind(str(row["governance_type"]))
            payload = str(row["canonical_json"])
            value = _MODELS[kind].model_validate_json(payload)
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError("stored governance object failed strict validation") from error
        if canonical_json(value) != payload:
            raise IntegrityError("stored governance object is not canonical JSON")
        digest = canonical_digest(value).removeprefix("sha256:")
        if digest != str(row["content_sha256"]):
            raise IntegrityError("stored governance object digest mismatch")
        if value.subject_id != self._subject_id:
            raise IntegrityError("stored governance object crossed the subject boundary")
        if _object_id(value) != str(row["object_id"]):
            raise IntegrityError("stored governance object identity mismatch")
        identity = (
            value
            if isinstance(value, SignerIdentity)
            else self._require_identity(connection, value.signature.signer_identity_id)
        )
        verify_signed_governance(value, identity)
        return value

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
