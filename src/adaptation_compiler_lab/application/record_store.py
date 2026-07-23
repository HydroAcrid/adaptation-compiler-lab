"""Adapter between strict domain records and the storage-neutral repository ports."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel

from adaptation_compiler_lab.domain.base import VersionedRecord
from adaptation_compiler_lab.domain.enums import RecordKind
from adaptation_compiler_lab.domain.references import ExactRecordRef
from adaptation_compiler_lab.persistence.ports import UnitOfWork, UnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import (
    LifecycleEvent,
    RecordKey,
    RecordLink,
    StoredRecord,
)
from adaptation_compiler_lab.serialization import (
    canonical_digest,
    canonical_json,
    deserialize_record,
)

CANONICALIZATION_VERSION = "1.0.0"
_AUXILIARY_RECORD_KINDS = frozenset({"release_candidate_snapshot"})


class DomainStoreError(ValueError):
    """Raised when a record graph cannot be persisted without losing integrity."""


@dataclass(frozen=True, slots=True)
class StoredDomainRecord:
    """Validated domain record paired with its immutable storage key."""

    key: RecordKey
    record: VersionedRecord


class DomainRecordStore:
    """Persist and recover exact versions while validating every reference digest."""

    def __init__(self, factory: UnitOfWorkFactory, *, subject_id: str) -> None:
        if not subject_id:
            raise DomainStoreError("subject_id must not be empty")
        self._factory = factory
        self._subject_id = subject_id

    def add_many(self, records: Iterable[VersionedRecord]) -> tuple[RecordKey, ...]:
        """Atomically add records first, then their exact-version reference graph.

        Adding all record snapshots before links permits legitimate mutually referential capture
        envelopes such as a TaskRecord that names prompt Evidence whose own provenance names the
        TaskRecord.
        """

        ordered = tuple(
            sorted(
                records,
                key=lambda item: (item.record_type.value, item.record_id, item.record_version),
            )
        )
        keys = tuple(_record_key(record) for record in ordered)
        if len(keys) != len(set(keys)):
            raise DomainStoreError("record batch contains duplicate exact identities")

        with self._factory(write=True) as unit_of_work:
            for record in ordered:
                _validate_subject(record, self._subject_id)
                unit_of_work.records.add(_stored_record(record, self._subject_id))
            for record in ordered:
                _add_links(unit_of_work, record)
            unit_of_work.commit()
        return keys

    def add(self, record: VersionedRecord) -> RecordKey:
        return self.add_many((record,))[0]

    def add_with_lifecycle(
        self,
        record: VersionedRecord,
        lifecycle_events: Iterable[LifecycleEvent],
    ) -> RecordKey:
        """Atomically add one immutable record, its links, and lifecycle history."""

        key = _record_key(record)
        events = tuple(lifecycle_events)
        if not events:
            raise DomainStoreError("atomic lifecycle persistence requires at least one event")
        for event in events:
            if event.entity != key:
                raise DomainStoreError("lifecycle event does not target the exact record")
            if event.policy_version != record.policy_version:
                raise DomainStoreError("lifecycle event policy does not match the record")
        with self._factory(write=True) as unit_of_work:
            _validate_subject(record, self._subject_id)
            unit_of_work.records.add(_stored_record(record, self._subject_id))
            _add_links(unit_of_work, record)
            for event in events:
                unit_of_work.lifecycle.append(event)
            unit_of_work.commit()
        return key

    def get(self, key: RecordKey) -> StoredDomainRecord | None:
        with self._factory(write=False) as unit_of_work:
            stored = unit_of_work.records.get(key)
        if stored is None:
            return None
        if stored.subject_id != self._subject_id:
            # A globally keyed row owned by another subject is indistinguishable from absence to
            # this subject-scoped adapter.  It must never be decoded or disclosed cross-subject.
            return None
        return _decode_stored_record(
            stored,
            subject_id=self._subject_id,
            expected_key=key,
        )

    def require(self, key: RecordKey) -> StoredDomainRecord:
        result = self.get(key)
        if result is None:
            raise DomainStoreError(f"domain record not found: {key}")
        return result

    def current_lifecycle_state(self, key: RecordKey) -> str | None:
        """Return the append-only lifecycle overlay for an exact subject-owned record."""

        if self.get(key) is None:
            return None
        with self._factory(write=False) as unit_of_work:
            return unit_of_work.lifecycle.current_state(key)

    def list(
        self, *, record_kind: str | None = None, benchmark_role: str | None = None
    ) -> tuple[StoredDomainRecord, ...]:
        domain_kinds = {kind.value for kind in RecordKind}
        if record_kind in _AUXILIARY_RECORD_KINDS:
            return ()
        if record_kind is not None and record_kind not in domain_kinds:
            raise DomainStoreError("requested record kind is not a supported domain record kind")
        with self._factory(write=False) as unit_of_work:
            stored_records = unit_of_work.records.list_records(
                kind=record_kind,
                subject_id=self._subject_id,
                benchmark_role=benchmark_role,
            )
        decoded: list[StoredDomainRecord] = []
        for stored in stored_records:
            if stored.key.kind in _AUXILIARY_RECORD_KINDS:
                continue
            if stored.key.kind not in domain_kinds:
                raise DomainStoreError("stored record kind is not a supported domain record kind")
            decoded.append(
                _decode_stored_record(
                    stored,
                    subject_id=self._subject_id,
                    expected_key=stored.key,
                )
            )
        return tuple(decoded)


def _record_key(record: VersionedRecord) -> RecordKey:
    return RecordKey(
        kind=record.record_type.value,
        record_id=record.record_id,
        version=record.record_version,
    )


def _stored_record(record: VersionedRecord, subject_id: str) -> StoredRecord:
    digest = str(canonical_digest(record)).removeprefix("sha256:")
    privacy_class, benchmark_role = _metadata(record)
    return StoredRecord(
        key=_record_key(record),
        schema_version=record.schema_version,
        canonicalization_version=CANONICALIZATION_VERSION,
        canonical_json=canonical_json(record),
        content_sha256=digest,
        created_at=record.created_at.isoformat(),
        subject_id=subject_id,
        privacy_class=privacy_class,
        benchmark_role=benchmark_role,
    )


def _decode_stored_record(
    stored: StoredRecord,
    *,
    subject_id: str,
    expected_key: RecordKey,
) -> StoredDomainRecord:
    """Validate every persisted projection before returning a trusted domain record."""

    if stored.subject_id != subject_id:
        raise DomainStoreError("stored domain record crossed the configured subject boundary")
    if stored.key != expected_key:
        raise DomainStoreError("stored domain record key does not match the requested key")
    if stored.key.kind not in {kind.value for kind in RecordKind}:
        raise DomainStoreError("stored record kind is not a supported domain record kind")
    if stored.schema_version not in {"1.0", "1.1"}:
        raise DomainStoreError("stored domain record has an unsupported schema version")
    if stored.canonicalization_version != CANONICALIZATION_VERSION:
        raise DomainStoreError("stored domain record has an unsupported canonicalization version")

    try:
        record = deserialize_record(stored.canonical_json)
    except (TypeError, ValueError) as error:
        raise DomainStoreError("stored domain record payload failed strict validation") from error

    actual_key = _record_key(record)
    if stored.key != actual_key:
        raise DomainStoreError("stored domain record payload does not match its immutable key")
    if stored.schema_version != record.schema_version:
        raise DomainStoreError("stored domain record schema metadata does not match its payload")

    expected_json = canonical_json(record)
    if stored.canonical_json != expected_json:
        raise DomainStoreError("stored domain record payload is not exact canonical JSON")
    expected_digest = str(canonical_digest(record)).removeprefix("sha256:")
    if stored.content_sha256 != expected_digest:
        raise DomainStoreError("stored domain record content digest does not match its payload")
    if stored.created_at != record.created_at.isoformat():
        raise DomainStoreError("stored domain record creation metadata does not match its payload")

    expected_privacy, expected_benchmark_role = _metadata(record)
    if stored.privacy_class != expected_privacy:
        raise DomainStoreError("stored domain record privacy metadata does not match its payload")
    if stored.benchmark_role != expected_benchmark_role:
        raise DomainStoreError("stored domain record benchmark metadata does not match its payload")
    _validate_subject(record, subject_id)
    return StoredDomainRecord(key=actual_key, record=record)


def _metadata(record: VersionedRecord) -> tuple[str, str]:
    payload = cast(Mapping[str, object], record.model_dump(mode="json"))
    privacy = payload.get("privacy")
    privacy_class = "internal"
    if isinstance(privacy, Mapping):
        sensitivity = privacy.get("sensitivity")
        if isinstance(sensitivity, str):
            privacy_class = sensitivity
    partition = payload.get("partition")
    benchmark_role = partition if isinstance(partition, str) else "construction"
    return privacy_class, benchmark_role


def _validate_subject(record: VersionedRecord, subject_id: str) -> None:
    payload = cast(Mapping[str, object], record.model_dump(mode="json"))
    declared_subject = payload.get("subject_id")
    if declared_subject is not None and declared_subject != subject_id:
        raise DomainStoreError("record subject does not match the workspace subject")
    scope = payload.get("scope")
    if isinstance(scope, Mapping):
        subjects = scope.get("subject_ids")
        if not isinstance(subjects, Sequence) or isinstance(subjects, str):
            raise DomainStoreError("record scope lacks a valid subject boundary")
        # This is a deliberately single-subject workspace.  A shared scope would make a
        # global exact-record key readable through more than one subject adapter, so it is
        # rejected until a future architecture introduces explicit shared-record semantics.
        if tuple(subjects) != (subject_id,):
            raise DomainStoreError("record scope must contain only the workspace subject")


def _add_links(unit_of_work: UnitOfWork, record: VersionedRecord) -> None:
    source = _record_key(record)
    for ordinal, (path, reference) in enumerate(_walk_refs(record)):
        target = RecordKey(
            kind=reference.record_type.value,
            record_id=reference.record_id,
            version=reference.record_version,
        )
        stored_target = unit_of_work.records.get(target)
        if stored_target is None:
            raise DomainStoreError(f"dangling exact reference at {path}: {target}")
        if reference.content_digest is not None:
            expected = reference.content_digest.removeprefix("sha256:")
            if stored_target.content_sha256 != expected:
                raise DomainStoreError(f"reference digest mismatch at {path}: {target}")
        unit_of_work.links.add(
            RecordLink(
                source=source,
                target=target,
                relation=path,
                ordinal=ordinal,
                created_at=record.created_at.isoformat(),
            )
        )


def _walk_refs(value: object, path: str = "$") -> Iterator[tuple[str, ExactRecordRef]]:
    if isinstance(value, ExactRecordRef):
        yield path, value
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _walk_refs(getattr(value, name), f"{path}.{name}")
        return
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield from _walk_refs(value[key], f"{path}.{key}")
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            yield from _walk_refs(item, f"{path}[{index}]")
