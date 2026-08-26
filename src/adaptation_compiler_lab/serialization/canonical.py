"""Deterministic JSON and content digests for domain contracts."""

import hashlib
import json
from collections.abc import Mapping
from typing import TypeVar

from pydantic import BaseModel

from adaptation_compiler_lab.domain.base import Sha256Digest, VersionedRecord
from adaptation_compiler_lab.domain.enums import RecordKind
from adaptation_compiler_lab.domain.records import (
    Artifact,
    EvaluationCase,
    Evidence,
    EvidenceV1,
    LessonCandidate,
    Outcome,
    Release,
    TargetPack,
    TaskRecord,
)
from adaptation_compiler_lab.domain.references import (
    AnyRecordRef,
    ArtifactRef,
    EvaluationCaseRef,
    EvidenceRef,
    LessonCandidateRef,
    OutcomeRef,
    ReleaseRef,
    TargetPackRef,
    TaskRecordRef,
)

RecordT = TypeVar("RecordT", bound=VersionedRecord)

RECORD_MODELS: Mapping[RecordKind, type[VersionedRecord]] = {
    RecordKind.TASK_RECORD: TaskRecord,
    RecordKind.OUTCOME: Outcome,
    RecordKind.EVIDENCE: Evidence,
    RecordKind.EVALUATION_CASE: EvaluationCase,
    RecordKind.LESSON_CANDIDATE: LessonCandidate,
    RecordKind.ARTIFACT: Artifact,
    RecordKind.RELEASE: Release,
    RecordKind.TARGET_PACK: TargetPack,
}

RECORD_MODELS_V1: Mapping[RecordKind, type[VersionedRecord]] = {
    **RECORD_MODELS,
    RecordKind.EVIDENCE: EvidenceV1,
}


def canonical_json(value: BaseModel | Mapping[str, object]) -> str:
    """Serialize a validated value with stable keys, spacing, Unicode, and null handling."""

    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json", exclude_none=False, round_trip=True)
        # The v1.0 canonical byte contract predates signed governance references. Keeping those
        # absent fields out preserves every existing synthetic digest and reference exactly.
        if isinstance(value, Evidence) and value.schema_version == "1.0":
            payload.pop("consent_receipt_ref", None)
            payload.pop("capture_receipt_ref", None)
    else:
        payload = dict(value)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    return canonical_json(value).encode("utf-8")


def canonical_digest(value: BaseModel | Mapping[str, object]) -> Sha256Digest:
    digest = hashlib.sha256(canonical_bytes(value)).hexdigest()
    return f"sha256:{digest}"


def record_ref(record: VersionedRecord) -> AnyRecordRef:
    """Create an exact, digest-bearing reference to a validated top-level record."""

    if record.record_type is RecordKind.TASK_RECORD:
        return TaskRecordRef(record_id=record.record_id, record_version=record.record_version)
    content_digest = canonical_digest(record)
    if record.record_type is RecordKind.OUTCOME:
        return OutcomeRef(
            record_id=record.record_id,
            record_version=record.record_version,
            content_digest=content_digest,
        )
    if record.record_type is RecordKind.EVIDENCE:
        return EvidenceRef(
            record_id=record.record_id,
            record_version=record.record_version,
            content_digest=content_digest,
        )
    if record.record_type is RecordKind.EVALUATION_CASE:
        return EvaluationCaseRef(
            record_id=record.record_id,
            record_version=record.record_version,
            content_digest=content_digest,
        )
    if record.record_type is RecordKind.LESSON_CANDIDATE:
        return LessonCandidateRef(
            record_id=record.record_id,
            record_version=record.record_version,
            content_digest=content_digest,
        )
    if record.record_type is RecordKind.ARTIFACT:
        return ArtifactRef(
            record_id=record.record_id,
            record_version=record.record_version,
            content_digest=content_digest,
        )
    if record.record_type is RecordKind.RELEASE:
        return ReleaseRef(
            record_id=record.record_id,
            record_version=record.record_version,
            content_digest=content_digest,
        )
    if record.record_type is RecordKind.TARGET_PACK:
        return TargetPackRef(
            record_id=record.record_id,
            record_version=record.record_version,
            content_digest=content_digest,
        )
    raise TypeError(f"unsupported record type: {record.record_type!r}")


def reference_matches(reference: AnyRecordRef, record: VersionedRecord) -> bool:
    return (
        reference.record_type is record.record_type
        and reference.record_id == record.record_id
        and reference.record_version == record.record_version
        and (
            reference.content_digest is None or reference.content_digest == canonical_digest(record)
        )
    )


def deserialize_record(payload: str | bytes) -> VersionedRecord:
    """Strictly decode a supported version 1 record from canonical or ordinary JSON."""

    raw = json.loads(payload)
    if not isinstance(raw, dict):
        raise ValueError("top-level record JSON must be an object")
    record_type_raw = raw.get("record_type")
    schema_version = raw.get("schema_version")
    if schema_version not in {"1.0", "1.1"}:
        raise ValueError(f"unsupported schema version: {schema_version!r}")
    if not isinstance(record_type_raw, str):
        raise ValueError(f"unsupported record type: {record_type_raw!r}")
    try:
        record_kind = RecordKind(record_type_raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"unsupported record type: {record_type_raw!r}") from error
    if schema_version == "1.1" and record_kind is not RecordKind.EVIDENCE:
        raise ValueError("schema version 1.1 is defined only for Evidence")
    model = RECORD_MODELS[record_kind]
    return model.model_validate_json(payload)


def round_trip(record: RecordT) -> RecordT:  # noqa: UP047
    parsed = deserialize_record(canonical_json(record))
    if type(parsed) is not type(record):
        raise TypeError("record type changed during canonical round trip")
    return parsed
