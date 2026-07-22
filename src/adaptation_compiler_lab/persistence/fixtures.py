"""Deterministic, idempotent loading of synthetic persistence fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from adaptation_compiler_lab.persistence.errors import FixtureConflictError, IntegrityError
from adaptation_compiler_lab.persistence.ports import UnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import (
    ActivationEvent,
    FixtureSet,
    LifecycleEvent,
    RecordLink,
    StoredRecord,
)


@dataclass(frozen=True, slots=True)
class FixtureBundle:
    """Fully specified synthetic fixture data with no generated IDs or timestamps."""

    fixture_set_id: str
    loaded_at: str
    records: tuple[StoredRecord, ...]
    links: tuple[RecordLink, ...] = ()
    lifecycle_events: tuple[LifecycleEvent, ...] = ()
    activation_events: tuple[ActivationEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class FixtureLoadResult:
    """Deterministic summary of a fixture load."""

    fixture_set_id: str
    manifest_sha256: str
    already_loaded: bool
    record_count: int
    link_count: int
    lifecycle_event_count: int
    activation_event_count: int


def _record_value(record: StoredRecord) -> dict[str, object]:
    return {
        "key": [record.key.kind, record.key.record_id, record.key.version],
        "schema_version": record.schema_version,
        "canonicalization_version": record.canonicalization_version,
        "canonical_json": record.canonical_json,
        "content_sha256": record.content_sha256,
        "created_at": record.created_at,
        "subject_id": record.subject_id,
        "privacy_class": record.privacy_class,
        "benchmark_role": record.benchmark_role,
    }


def _link_value(link: RecordLink) -> dict[str, object]:
    return {
        "source": [link.source.kind, link.source.record_id, link.source.version],
        "target": [link.target.kind, link.target.record_id, link.target.version],
        "relation": link.relation,
        "ordinal": link.ordinal,
        "created_at": link.created_at,
    }


def _lifecycle_value(event: LifecycleEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "entity": [event.entity.kind, event.entity.record_id, event.entity.version],
        "from_state": event.from_state,
        "to_state": event.to_state,
        "previous_event_id": event.previous_event_id,
        "actor_id": event.actor_id,
        "policy_version": event.policy_version,
        "reason": event.reason,
        "occurred_at": event.occurred_at,
        "canonical_json": event.canonical_json,
        "event_sha256": event.event_sha256,
    }


def _activation_value(event: ActivationEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "environment_id": event.environment_id,
        "action": event.action,
        "release": (
            None
            if event.release is None
            else [event.release.kind, event.release.record_id, event.release.version]
        ),
        "target_pack": (
            None
            if event.target_pack is None
            else [event.target_pack.kind, event.target_pack.record_id, event.target_pack.version]
        ),
        "previous_event_id": event.previous_event_id,
        "actor_id": event.actor_id,
        "reason": event.reason,
        "occurred_at": event.occurred_at,
        "canonical_json": event.canonical_json,
        "event_sha256": event.event_sha256,
    }


def _manifest_sha256(bundle: FixtureBundle, loader_version: str) -> str:
    value = {
        "fixture_set_id": bundle.fixture_set_id,
        "loaded_at": bundle.loaded_at,
        "loader_version": loader_version,
        "records": [
            _record_value(record) for record in sorted(bundle.records, key=lambda item: item.key)
        ],
        "links": [
            _link_value(link)
            for link in sorted(
                bundle.links,
                key=lambda item: (
                    item.source,
                    item.relation,
                    item.ordinal,
                    item.target,
                ),
            )
        ],
        "lifecycle_events": [
            _lifecycle_value(event)
            for event in sorted(
                bundle.lifecycle_events,
                key=lambda item: (item.entity, item.occurred_at, item.event_id),
            )
        ],
        "activation_events": [
            _activation_value(event)
            for event in sorted(
                bundle.activation_events,
                key=lambda item: (item.environment_id, item.occurred_at, item.event_id),
            )
        ],
    }
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _order_lifecycle(events: tuple[LifecycleEvent, ...]) -> tuple[LifecycleEvent, ...]:
    remaining = {event.event_id: event for event in events}
    if len(remaining) != len(events):
        raise IntegrityError("fixture contains duplicate lifecycle event IDs")
    ordered: list[LifecycleEvent] = []
    heads: dict[tuple[str, str, str], str | None] = {}
    while remaining:
        eligible = [
            event
            for event in remaining.values()
            if event.previous_event_id
            == heads.get((event.entity.kind, event.entity.record_id, event.entity.version))
        ]
        if not eligible:
            raise IntegrityError(
                "fixture lifecycle history is cyclic or references a missing event"
            )
        event = min(eligible, key=lambda item: (item.entity, item.event_id))
        stream = (event.entity.kind, event.entity.record_id, event.entity.version)
        heads[stream] = event.event_id
        ordered.append(event)
        del remaining[event.event_id]
    return tuple(ordered)


def _order_activations(events: tuple[ActivationEvent, ...]) -> tuple[ActivationEvent, ...]:
    remaining = {event.event_id: event for event in events}
    if len(remaining) != len(events):
        raise IntegrityError("fixture contains duplicate activation event IDs")
    ordered: list[ActivationEvent] = []
    heads: dict[str, str | None] = {}
    while remaining:
        eligible = [
            event
            for event in remaining.values()
            if event.previous_event_id == heads.get(event.environment_id)
        ]
        if not eligible:
            raise IntegrityError(
                "fixture activation history is cyclic or references a missing event"
            )
        event = min(eligible, key=lambda item: (item.environment_id, item.event_id))
        heads[event.environment_id] = event.event_id
        ordered.append(event)
        del remaining[event.event_id]
    return tuple(ordered)


class FixtureLoader:
    """Load a fixture bundle in one transaction and refuse identity reuse."""

    def __init__(
        self, unit_of_work_factory: UnitOfWorkFactory, *, loader_version: str = "1"
    ) -> None:
        self._factory = unit_of_work_factory
        self._loader_version = loader_version

    def load(self, bundle: FixtureBundle) -> FixtureLoadResult:
        """Load ``bundle`` or return an exact-repeat no-op result."""

        if not bundle.fixture_set_id:
            raise IntegrityError("fixture_set_id must not be empty")
        digest = _manifest_sha256(bundle, self._loader_version)
        fixture_set = FixtureSet(
            fixture_set_id=bundle.fixture_set_id,
            manifest_sha256=digest,
            loader_version=self._loader_version,
            record_count=len(bundle.records),
            link_count=len(bundle.links),
            lifecycle_event_count=len(bundle.lifecycle_events),
            activation_event_count=len(bundle.activation_events),
            loaded_at=bundle.loaded_at,
        )

        def result(*, already_loaded: bool) -> FixtureLoadResult:
            return FixtureLoadResult(
                fixture_set_id=bundle.fixture_set_id,
                manifest_sha256=digest,
                already_loaded=already_loaded,
                record_count=len(bundle.records),
                link_count=len(bundle.links),
                lifecycle_event_count=len(bundle.lifecycle_events),
                activation_event_count=len(bundle.activation_events),
            )

        with self._factory(write=True) as unit_of_work:
            existing = unit_of_work.fixture_sets.get(bundle.fixture_set_id)
            if existing is not None:
                if existing != fixture_set:
                    raise FixtureConflictError(
                        "fixture-set identifier was reused for a different deterministic manifest"
                    )
                return result(already_loaded=True)

            for record in sorted(bundle.records, key=lambda item: item.key):
                unit_of_work.records.add(record)
            for link in sorted(
                bundle.links,
                key=lambda item: (item.source, item.relation, item.ordinal, item.target),
            ):
                unit_of_work.links.add(link)
            for lifecycle_event in _order_lifecycle(bundle.lifecycle_events):
                unit_of_work.lifecycle.append(lifecycle_event)
            activation_heads: dict[str, str | None] = {}
            for activation_event in _order_activations(bundle.activation_events):
                expected = activation_heads.get(activation_event.environment_id)
                unit_of_work.activations.append(
                    activation_event,
                    expected_previous_event_id=expected,
                )
                activation_heads[activation_event.environment_id] = activation_event.event_id
            unit_of_work.fixture_sets.add(fixture_set)
            unit_of_work.commit()

        return result(already_loaded=False)
