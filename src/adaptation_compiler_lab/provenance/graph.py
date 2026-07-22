"""Exact-reference resolution and cycle detection for immutable record graphs."""

from collections.abc import Iterable, Mapping

from adaptation_compiler_lab.domain.base import VersionedRecord
from adaptation_compiler_lab.domain.enums import RecordKind
from adaptation_compiler_lab.domain.records import Evidence
from adaptation_compiler_lab.domain.references import AnyRecordRef
from adaptation_compiler_lab.serialization import reference_matches

RecordKey = tuple[RecordKind, str, str]
RecordIndex = Mapping[RecordKey, VersionedRecord]


def record_key(record: VersionedRecord) -> RecordKey:
    return (record.record_type, record.record_id, record.record_version)


def reference_key(reference: AnyRecordRef) -> RecordKey:
    return (reference.record_type, reference.record_id, reference.record_version)


def index_records(records: Iterable[VersionedRecord]) -> dict[RecordKey, VersionedRecord]:
    index: dict[RecordKey, VersionedRecord] = {}
    for record in records:
        key = record_key(record)
        if key in index:
            raise ValueError(f"duplicate exact record version: {key!r}")
        index[key] = record
    return index


def resolve_reference(index: RecordIndex, reference: AnyRecordRef) -> VersionedRecord | None:
    record = index.get(reference_key(reference))
    if record is None or not reference_matches(reference, record):
        return None
    return record


def evidence_cycle(evidence: Iterable[Evidence]) -> tuple[str, ...] | None:
    """Return one evidence-id cycle, or ``None`` when derivation lineage is acyclic."""

    records = tuple(evidence)
    by_key = {record_key(item): item for item in records}
    visiting: set[RecordKey] = set()
    visited: set[RecordKey] = set()
    path: list[RecordKey] = []

    def visit(key: RecordKey) -> tuple[str, ...] | None:
        if key in visiting:
            start = path.index(key)
            return tuple(item[1] for item in (*path[start:], key))
        if key in visited:
            return None
        record = by_key.get(key)
        if record is None:
            return None
        visiting.add(key)
        path.append(key)
        for parent in record.parent_evidence_refs:
            cycle = visit(reference_key(parent))
            if cycle is not None:
                return cycle
        path.pop()
        visiting.remove(key)
        visited.add(key)
        return None

    for candidate in by_key:
        cycle = visit(candidate)
        if cycle is not None:
            return cycle
    return None
