"""Storage-neutral immutable data transfer objects.

These types deliberately know nothing about Pydantic or the domain model package.  An
application-layer codec is responsible for validating domain objects and producing canonical
JSON before records reach persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


def sha256_text(value: str) -> str:
    """Return the lowercase SHA-256 digest of UTF-8 text."""

    return sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, order=True, slots=True)
class RecordKey:
    """Exact identity for one immutable domain-record version."""

    kind: str
    record_id: str
    version: str


@dataclass(frozen=True, slots=True)
class StoredRecord:
    """Canonical serialized domain record plus query-safe metadata projections."""

    key: RecordKey
    schema_version: str
    canonicalization_version: str
    canonical_json: str
    content_sha256: str
    created_at: str
    subject_id: str
    privacy_class: str
    benchmark_role: str


@dataclass(frozen=True, slots=True)
class RecordLink:
    """Typed exact-version relationship in the provenance graph."""

    source: RecordKey
    target: RecordKey
    relation: str
    ordinal: int
    created_at: str


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """One append-only lifecycle transition for an immutable record."""

    event_id: str
    entity: RecordKey
    from_state: str | None
    to_state: str
    previous_event_id: str | None
    actor_id: str
    policy_version: str
    reason: str
    occurred_at: str
    canonical_json: str
    event_sha256: str


@dataclass(frozen=True, slots=True)
class ActivationEvent:
    """One append-only environment activation-pointer change."""

    event_id: str
    environment_id: str
    action: str
    release: RecordKey | None
    target_pack: RecordKey | None
    previous_event_id: str | None
    actor_id: str
    reason: str
    occurred_at: str
    canonical_json: str
    event_sha256: str


@dataclass(frozen=True, slots=True)
class FixtureSet:
    """Audit record for an idempotently loaded deterministic fixture bundle."""

    fixture_set_id: str
    manifest_sha256: str
    loader_version: str
    record_count: int
    link_count: int
    lifecycle_event_count: int
    activation_event_count: int
    loaded_at: str
