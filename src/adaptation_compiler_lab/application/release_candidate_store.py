"""Persistent immutable snapshots for the non-domain ReleaseCandidate workflow."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from adaptation_compiler_lab.domain import ReleaseCandidateState
from adaptation_compiler_lab.persistence.errors import RecordConflictError
from adaptation_compiler_lab.persistence.ports import UnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import RecordKey, StoredRecord
from adaptation_compiler_lab.release.proposals import ReleaseCandidate
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

RELEASE_CANDIDATE_SNAPSHOT_KIND = "release_candidate_snapshot"
_SNAPSHOT_SCHEMA_VERSION = "1.0"
_CANONICALIZATION_VERSION = "application-release-candidate-1.0.0"


class ReleaseCandidateStoreError(ValueError):
    """Base error for invalid or unavailable candidate snapshots."""


class ReleaseCandidateSnapshotConflictError(ReleaseCandidateStoreError):
    """An immutable snapshot key was reused for divergent candidate content."""


class ReleaseCandidateSnapshotIntegrityError(ReleaseCandidateStoreError):
    """Stored candidate bytes, digest, or identity failed verification."""


class ReleaseCandidateSnapshotNotFoundError(ReleaseCandidateStoreError):
    """An exact subject-scoped candidate snapshot does not exist."""


@dataclass(frozen=True, order=True, slots=True)
class ReleaseCandidateSnapshotKey:
    """Application identity for one candidate disposition snapshot."""

    candidate_id: str
    candidate_version: str
    disposition_id: str


@dataclass(frozen=True, slots=True)
class StoredReleaseCandidateSnapshot:
    """Validated candidate snapshot paired with its exact application identity."""

    key: ReleaseCandidateSnapshotKey
    candidate: ReleaseCandidate
    content_digest: str


class ReleaseCandidateSnapshotStore:
    """Store candidate dispositions beside domain records without treating them as domain data."""

    def __init__(self, factory: UnitOfWorkFactory, *, subject_id: str) -> None:
        if not subject_id:
            raise ReleaseCandidateStoreError("subject_id must not be empty")
        self._factory = factory
        self._subject_id = subject_id

    def put(self, candidate: ReleaseCandidate) -> StoredReleaseCandidateSnapshot:
        """Idempotently persist the candidate's latest immutable disposition snapshot."""

        key = _snapshot_key(candidate)
        payload = canonical_json(candidate)
        digest = str(canonical_digest(candidate)).removeprefix("sha256:")
        record = StoredRecord(
            key=self._storage_key(key),
            schema_version=_SNAPSHOT_SCHEMA_VERSION,
            canonicalization_version=_CANONICALIZATION_VERSION,
            canonical_json=payload,
            content_sha256=digest,
            created_at=candidate.dispositions[-1].decided_at.isoformat(),
            subject_id=self._subject_id,
            privacy_class="internal",
            benchmark_role="construction",
        )
        try:
            with self._factory(write=True) as unit_of_work:
                unit_of_work.records.add(record)
                unit_of_work.commit()
        except RecordConflictError as error:
            raise ReleaseCandidateSnapshotConflictError(
                "candidate snapshot identity already names different immutable content"
            ) from error
        return StoredReleaseCandidateSnapshot(
            key=key,
            candidate=candidate,
            content_digest=f"sha256:{digest}",
        )

    def get(self, key: ReleaseCandidateSnapshotKey) -> StoredReleaseCandidateSnapshot | None:
        """Return an exact snapshot only within this store's subject namespace."""

        with self._factory(write=False) as unit_of_work:
            record = unit_of_work.records.get(self._storage_key(key))
        if record is None or record.subject_id != self._subject_id:
            return None
        return self._decode(record, expected_key=key)

    def require(self, key: ReleaseCandidateSnapshotKey) -> StoredReleaseCandidateSnapshot:
        """Return an exact snapshot or raise a stable application error."""

        snapshot = self.get(key)
        if snapshot is None:
            raise ReleaseCandidateSnapshotNotFoundError(
                f"release candidate snapshot not found: {key}"
            )
        return snapshot

    def list(
        self,
        *,
        candidate_id: str | None = None,
        state: ReleaseCandidateState | None = None,
    ) -> tuple[StoredReleaseCandidateSnapshot, ...]:
        """List deterministic, subject-isolated candidate snapshots."""

        with self._factory(write=False) as unit_of_work:
            records = unit_of_work.records.list_records(
                kind=RELEASE_CANDIDATE_SNAPSHOT_KIND,
                subject_id=self._subject_id,
            )
        snapshots = tuple(self._decode(record) for record in records)
        filtered = tuple(
            snapshot
            for snapshot in snapshots
            if (candidate_id is None or snapshot.key.candidate_id == candidate_id)
            and (state is None or snapshot.candidate.state is state)
        )
        return tuple(
            sorted(
                filtered,
                key=lambda snapshot: (
                    snapshot.key.candidate_id,
                    snapshot.key.candidate_version,
                    snapshot.candidate.dispositions[-1].decided_at,
                    snapshot.key.disposition_id,
                ),
            )
        )

    def _storage_key(self, key: ReleaseCandidateSnapshotKey) -> RecordKey:
        # Length-prefixing makes the namespace injective even though Identifier permits colons.
        namespaced_id = f"{len(self._subject_id)}:{self._subject_id}{key.candidate_id}"
        snapshot_version = (
            f"{len(key.candidate_version)}:{key.candidate_version}{key.disposition_id}"
        )
        return RecordKey(
            kind=RELEASE_CANDIDATE_SNAPSHOT_KIND,
            record_id=namespaced_id,
            version=snapshot_version,
        )

    def _decode(
        self,
        record: StoredRecord,
        *,
        expected_key: ReleaseCandidateSnapshotKey | None = None,
    ) -> StoredReleaseCandidateSnapshot:
        if record.key.kind != RELEASE_CANDIDATE_SNAPSHOT_KIND:
            raise ReleaseCandidateSnapshotIntegrityError("unexpected snapshot record kind")
        if record.subject_id != self._subject_id:
            raise ReleaseCandidateSnapshotIntegrityError("candidate snapshot crossed subject scope")
        if record.schema_version != _SNAPSHOT_SCHEMA_VERSION:
            raise ReleaseCandidateSnapshotIntegrityError("unsupported candidate snapshot schema")
        if record.canonicalization_version != _CANONICALIZATION_VERSION:
            raise ReleaseCandidateSnapshotIntegrityError(
                "unsupported candidate canonicalization version"
            )
        try:
            candidate = ReleaseCandidate.model_validate_json(record.canonical_json)
        except ValidationError as error:
            raise ReleaseCandidateSnapshotIntegrityError(
                "stored candidate snapshot failed strict validation"
            ) from error
        payload = canonical_json(candidate)
        digest = str(canonical_digest(candidate)).removeprefix("sha256:")
        if payload != record.canonical_json or digest != record.content_sha256:
            raise ReleaseCandidateSnapshotIntegrityError(
                "stored candidate snapshot is non-canonical or digest-mismatched"
            )
        key = _snapshot_key(candidate)
        if expected_key is not None and key != expected_key:
            raise ReleaseCandidateSnapshotIntegrityError(
                "stored candidate payload does not match its requested snapshot identity"
            )
        if self._storage_key(key) != record.key:
            raise ReleaseCandidateSnapshotIntegrityError(
                "stored candidate payload does not match its ledger key"
            )
        return StoredReleaseCandidateSnapshot(
            key=key,
            candidate=candidate,
            content_digest=f"sha256:{digest}",
        )


def _snapshot_key(candidate: ReleaseCandidate) -> ReleaseCandidateSnapshotKey:
    latest = candidate.dispositions[-1]
    return ReleaseCandidateSnapshotKey(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        disposition_id=latest.disposition_id,
    )
