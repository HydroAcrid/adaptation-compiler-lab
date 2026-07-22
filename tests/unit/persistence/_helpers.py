"""Deterministic inline DTO builders for persistence tests."""

from __future__ import annotations

import json

from adaptation_compiler_lab.persistence.records import (
    ActivationEvent,
    LifecycleEvent,
    RecordKey,
    StoredRecord,
    sha256_text,
)

STAMP = "2026-07-22T12:00:00+00:00"


def canonical(value: dict[str, object]) -> str:
    """Return deterministic JSON used as a stand-in for the domain codec."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def make_record(
    kind: str,
    record_id: str,
    version: str = "1",
    *,
    value: str = "fixture",
    benchmark_role: str = "construction",
) -> StoredRecord:
    """Build an immutable storage record with a valid digest."""

    payload = canonical(
        {
            "id": record_id,
            "kind": kind,
            "value": value,
            "version": version,
        }
    )
    return StoredRecord(
        key=RecordKey(kind, record_id, version),
        schema_version="1.0",
        canonicalization_version="1",
        canonical_json=payload,
        content_sha256=sha256_text(payload),
        created_at=STAMP,
        subject_id="subject-kevin",
        privacy_class="internal",
        benchmark_role=benchmark_role,
    )


def make_lifecycle(
    event_id: str,
    entity: RecordKey,
    to_state: str,
    *,
    previous: str | None = None,
    from_state: str | None = None,
) -> LifecycleEvent:
    """Build a deterministic lifecycle event."""

    payload = canonical(
        {
            "entity": [entity.kind, entity.record_id, entity.version],
            "event_id": event_id,
            "from": from_state,
            "previous": previous,
            "to": to_state,
        }
    )
    return LifecycleEvent(
        event_id=event_id,
        entity=entity,
        from_state=from_state,
        to_state=to_state,
        previous_event_id=previous,
        actor_id="reviewer-1",
        policy_version="1",
        reason="synthetic test transition",
        occurred_at=STAMP,
        canonical_json=payload,
        event_sha256=sha256_text(payload),
    )


def make_activation(
    event_id: str,
    action: str,
    *,
    release: RecordKey | None,
    target_pack: RecordKey | None,
    previous: str | None = None,
    environment_id: str = "local-dev",
) -> ActivationEvent:
    """Build a deterministic activation event."""

    payload = canonical(
        {
            "action": action,
            "environment_id": environment_id,
            "event_id": event_id,
            "previous": previous,
            "release": (
                None if release is None else [release.kind, release.record_id, release.version]
            ),
            "target_pack": (
                None
                if target_pack is None
                else [target_pack.kind, target_pack.record_id, target_pack.version]
            ),
        }
    )
    return ActivationEvent(
        event_id=event_id,
        environment_id=environment_id,
        action=action,
        release=release,
        target_pack=target_pack,
        previous_event_id=previous,
        actor_id="operator-1",
        reason="synthetic activation",
        occurred_at=STAMP,
        canonical_json=payload,
        event_sha256=sha256_text(payload),
    )
