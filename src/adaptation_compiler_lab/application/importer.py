"""Manually invoked, channel-preserving import of structured source bundles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import Field, model_validator

from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.domain.base import FrozenModel, Identifier, NonEmptyStr, SemVer
from adaptation_compiler_lab.domain.records import Evidence, Outcome, TaskRecord
from adaptation_compiler_lab.persistence.errors import PersistenceError
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.sanitization import is_sensitive_path, scan_text
from adaptation_compiler_lab.serialization import canonical_json, deserialize_record

MAX_BUNDLE_BYTES = 5 * 1024 * 1024


class BundleImportError(ValueError):
    """Raised when a source bundle cannot cross the raw-capture boundary safely."""


class InlinePayload(FrozenModel):
    """Synthetic/hand-authored UTF-8 payload associated with one Evidence version."""

    evidence_record_id: Identifier
    evidence_record_version: SemVer
    media_type: NonEmptyStr
    source_path: NonEmptyStr
    text: str


class TaskBundle(FrozenModel):
    """Versioned import envelope; it cannot contain candidates, artifacts, releases, or packs."""

    bundle_version: Literal["1.0"] = "1.0"
    subject_id: Identifier
    records: Annotated[tuple[dict[str, object], ...], Field(min_length=1)]
    raw_payloads: tuple[InlinePayload, ...] = ()

    @model_validator(mode="after")
    def unique_payload_keys(self) -> TaskBundle:
        keys = [
            (payload.evidence_record_id, payload.evidence_record_version)
            for payload in self.raw_payloads
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("bundle contains duplicate inline payload identities")
        return self


class ImportResult(FrozenModel):
    """Audit-safe result containing identities but no raw bytes."""

    imported_record_keys: tuple[NonEmptyStr, ...]
    raw_payload_refs: tuple[NonEmptyStr, ...]


def import_task_bundle(
    path: Path,
    *,
    expected_subject_id: str,
    record_store: DomainRecordStore,
    raw_store: LocalRawPayloadStore,
) -> ImportResult:
    """Validate an entire bundle before storing any raw bytes or record metadata."""

    resolved = path.expanduser().resolve()
    if is_sensitive_path(path) or is_sensitive_path(resolved):
        raise BundleImportError("bundle path is excluded by the sensitive-path policy")
    if not resolved.is_file():
        raise BundleImportError(f"bundle is not a regular file: {resolved}")
    if resolved.stat().st_size > MAX_BUNDLE_BYTES:
        raise BundleImportError("bundle exceeds the local import size limit")
    try:
        bundle = TaskBundle.model_validate_json(resolved.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise BundleImportError(f"bundle validation failed: {error}") from error
    if bundle.subject_id != expected_subject_id:
        raise BundleImportError("bundle subject does not match the workspace subject")

    records = tuple(deserialize_record(canonical_json(record)) for record in bundle.records)
    for record in records:
        if not isinstance(record, (TaskRecord, Outcome, Evidence)):
            raise BundleImportError(
                "source import accepts only TaskRecord, Outcome, and Evidence records"
            )
    source_records = cast(tuple[TaskRecord | Outcome | Evidence, ...], records)

    from adaptation_compiler_lab.provenance import validate_lineage

    trust_decision = validate_lineage(records)
    if not trust_decision.allowed:
        messages = "; ".join(violation.message for violation in trust_decision.violations)
        raise BundleImportError(f"bundle trust/provenance validation failed: {messages}")

    payloads = {
        (payload.evidence_record_id, payload.evidence_record_version): payload
        for payload in bundle.raw_payloads
    }
    expected_refs = _validate_payloads(source_records, payloads)

    # Preflight immutable record conflicts before creating raw-store entries.
    for record in records:
        from adaptation_compiler_lab.persistence.records import RecordKey

        record_key = RecordKey(record.record_type.value, record.record_id, record.record_version)
        existing = record_store.get(record_key)
        if existing is not None and existing.record != record:
            raise BundleImportError(
                f"immutable record identity already has other content: {record_key}"
            )

    stored_raw_refs: list[RawPayloadRef] = []
    newly_created_raw_refs: list[RawPayloadRef] = []
    try:
        for payload_key, payload in sorted(payloads.items()):
            expected = expected_refs[payload_key]
            existed = raw_store.contains(expected)
            reference = raw_store.put(payload.text.encode("utf-8"), media_type=payload.media_type)
            if reference != expected:
                raise BundleImportError(
                    "raw store returned metadata inconsistent with validated input"
                )
            stored_raw_refs.append(reference)
            if not existed and reference not in newly_created_raw_refs:
                newly_created_raw_refs.append(reference)
        stored_keys = record_store.add_many(records)
    except (OSError, PersistenceError, ValueError) as error:
        cleanup_failures = 0
        for reference in reversed(newly_created_raw_refs):
            try:
                raw_store.discard(reference)
            except (OSError, ValueError):
                cleanup_failures += 1
        cleanup_note = (
            f"; {cleanup_failures} new raw payload(s) require manual cleanup"
            if cleanup_failures
            else ""
        )
        raise BundleImportError(f"bundle persistence failed: {error}{cleanup_note}") from error
    return ImportResult(
        imported_record_keys=tuple(
            f"{key.kind}:{key.record_id}@{key.version}" for key in stored_keys
        ),
        raw_payload_refs=tuple(reference.relative_path for reference in stored_raw_refs),
    )


def _validate_payloads(
    records: tuple[TaskRecord | Outcome | Evidence, ...],
    payloads: Mapping[tuple[str, str], InlinePayload],
) -> dict[tuple[str, str], RawPayloadRef]:
    evidence_records = {
        (record.record_id, record.record_version): record
        for record in records
        if isinstance(record, Evidence) and record.payload is not None
    }
    if set(payloads) != set(evidence_records):
        raise BundleImportError(
            "inline payloads must exactly cover Evidence records that retain payload bytes"
        )
    expected: dict[tuple[str, str], RawPayloadRef] = {}
    for key, payload in payloads.items():
        if is_sensitive_path(payload.source_path):
            raise BundleImportError(f"payload source path is excluded: {payload.source_path}")
        report = scan_text(payload.text)
        if report.findings:
            kinds = ", ".join(sorted({finding.kind.value for finding in report.findings}))
            raise BundleImportError(f"raw payload contains prohibited secret-like content: {kinds}")
        encoded = payload.text.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        expected_ref = RawPayloadRef(
            sha256=digest,
            size_bytes=len(encoded),
            media_type=payload.media_type,
            relative_path=f"sha256/{digest[:2]}/{digest}",
        )
        evidence = evidence_records[key]
        domain_payload = evidence.payload
        if domain_payload is None:  # narrowed by evidence_records, retained for static safety
            raise BundleImportError("evidence payload metadata unexpectedly missing")
        if (
            domain_payload.content_digest != f"sha256:{expected_ref.sha256}"
            or domain_payload.byte_length != expected_ref.size_bytes
            or domain_payload.media_type != expected_ref.media_type
            or domain_payload.locator != expected_ref.relative_path
        ):
            raise BundleImportError(f"payload metadata mismatch for evidence {key[0]}@{key[1]}")
        expected[key] = expected_ref
    return expected


def load_bundle_mapping(path: Path) -> Mapping[str, object]:
    """Read a bundle for diagnostics without interpreting content as instruction."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise BundleImportError("bundle must be a JSON object")
    return cast(Mapping[str, object], payload)
