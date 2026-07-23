"""Repository and unit-of-work ports independent of SQLite and domain models."""

from __future__ import annotations

from typing import Protocol, Self

from adaptation_compiler_lab.persistence.records import (
    ActivationEvent,
    FixtureSet,
    LifecycleEvent,
    RecordKey,
    RecordLink,
    StoredRecord,
)


class RecordRepository(Protocol):
    """Store and retrieve exact immutable record snapshots."""

    def add(self, record: StoredRecord) -> bool: ...

    def get(self, key: RecordKey) -> StoredRecord | None: ...

    def require(self, key: RecordKey) -> StoredRecord: ...

    def list_versions(self, kind: str, record_id: str) -> tuple[StoredRecord, ...]: ...

    def list_records(
        self,
        *,
        kind: str | None = None,
        subject_id: str | None = None,
        benchmark_role: str | None = None,
    ) -> tuple[StoredRecord, ...]: ...


class LinkRepository(Protocol):
    """Store and traverse exact-version provenance links."""

    def add(self, link: RecordLink) -> bool: ...

    def outgoing(
        self, source: RecordKey, *, relation: str | None = None
    ) -> tuple[RecordLink, ...]: ...

    def incoming(
        self, target: RecordKey, *, relation: str | None = None
    ) -> tuple[RecordLink, ...]: ...


class LifecycleRepository(Protocol):
    """Append and inspect lifecycle history without mutating record content."""

    def append(self, event: LifecycleEvent) -> bool: ...

    def history(self, entity: RecordKey) -> tuple[LifecycleEvent, ...]: ...

    def current_state(self, entity: RecordKey) -> str | None: ...


class ActivationRepository(Protocol):
    """Append and inspect activation-pointer history."""

    def append(self, event: ActivationEvent, *, expected_previous_event_id: str | None) -> bool: ...

    def current(self, environment_id: str) -> ActivationEvent | None: ...

    def list_current(self) -> tuple[ActivationEvent, ...]: ...

    def history(self, environment_id: str) -> tuple[ActivationEvent, ...]: ...


class FixtureLedgerRepository(Protocol):
    """Track deterministic fixture bundle identities."""

    def get(self, fixture_set_id: str) -> FixtureSet | None: ...

    def add(self, fixture_set: FixtureSet) -> bool: ...


class UnitOfWork(Protocol):
    """Atomic collection of storage repositories."""

    records: RecordRepository
    links: LinkRepository
    lifecycle: LifecycleRepository
    activations: ActivationRepository
    fixture_sets: FixtureLedgerRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    """Create an isolated unit of work."""

    def __call__(self, *, write: bool = True) -> UnitOfWork: ...
