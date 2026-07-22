"""Canonical builders for append-only record lifecycle events."""

from __future__ import annotations

from datetime import datetime

from adaptation_compiler_lab.domain import ActorRef, SemVer
from adaptation_compiler_lab.persistence.records import LifecycleEvent, RecordKey
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def make_lifecycle_event(
    *,
    event_id: str,
    entity: RecordKey,
    from_state: str | None,
    to_state: str,
    previous_event_id: str | None,
    actor: ActorRef,
    policy_version: SemVer,
    reason: str,
    occurred_at: datetime,
) -> LifecycleEvent:
    """Build one canonical lifecycle event for atomic persistence."""

    payload = {
        "actor_id": actor.actor_id,
        "entity": {
            "kind": entity.kind,
            "record_id": entity.record_id,
            "version": entity.version,
        },
        "event_id": event_id,
        "from_state": from_state,
        "occurred_at": occurred_at.isoformat(),
        "policy_version": policy_version,
        "previous_event_id": previous_event_id,
        "reason": reason,
        "to_state": to_state,
    }
    serialized = canonical_json(payload)
    return LifecycleEvent(
        event_id=event_id,
        entity=entity,
        from_state=from_state,
        to_state=to_state,
        previous_event_id=previous_event_id,
        actor_id=actor.actor_id,
        policy_version=policy_version,
        reason=reason,
        occurred_at=occurred_at.isoformat(),
        canonical_json=serialized,
        event_sha256=str(canonical_digest(payload)).removeprefix("sha256:"),
    )


__all__ = ["make_lifecycle_event"]
