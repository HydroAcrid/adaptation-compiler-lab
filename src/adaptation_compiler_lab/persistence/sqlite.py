"""SQLite implementations of the model-agnostic persistence ports."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.persistence.errors import (
    FixtureConflictError,
    HistoryConflictError,
    RecordConflictError,
    RecordNotFoundError,
)
from adaptation_compiler_lab.persistence.errors import (
    IntegrityError as StorageIntegrityError,
)
from adaptation_compiler_lab.persistence.migrations import MigrationRunner
from adaptation_compiler_lab.persistence.ports import (
    ActivationRepository,
    FixtureLedgerRepository,
    LifecycleRepository,
    LinkRepository,
    RecordRepository,
)
from adaptation_compiler_lab.persistence.records import (
    ActivationEvent,
    FixtureSet,
    LifecycleEvent,
    RecordKey,
    RecordLink,
    StoredRecord,
    sha256_text,
)


def _required_text(value: str, field: str) -> None:
    if not value:
        raise StorageIntegrityError(f"{field} must not be empty")


def _validate_canonical_json(value: str, digest: str, field: str) -> None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise StorageIntegrityError(f"{field} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise StorageIntegrityError(f"{field} must encode a JSON object")
    if sha256_text(value) != digest:
        raise StorageIntegrityError(f"{field} SHA-256 does not match its canonical bytes")


def _key_values(key: RecordKey) -> tuple[str, str, str]:
    return key.kind, key.record_id, key.version


def _row_text(row: sqlite3.Row, field: str) -> str:
    return cast(str, row[field])


def _row_optional_text(row: sqlite3.Row, field: str) -> str | None:
    value = row[field]
    return None if value is None else cast(str, value)


def _record_from_row(row: sqlite3.Row) -> StoredRecord:
    return StoredRecord(
        key=RecordKey(
            kind=_row_text(row, "record_kind"),
            record_id=_row_text(row, "record_id"),
            version=_row_text(row, "record_version"),
        ),
        schema_version=_row_text(row, "schema_version"),
        canonicalization_version=_row_text(row, "canonicalization_version"),
        canonical_json=_row_text(row, "canonical_json"),
        content_sha256=_row_text(row, "content_sha256"),
        created_at=_row_text(row, "created_at"),
        subject_id=_row_text(row, "subject_id"),
        privacy_class=_row_text(row, "privacy_class"),
        benchmark_role=_row_text(row, "benchmark_role"),
    )


def _link_from_row(row: sqlite3.Row) -> RecordLink:
    return RecordLink(
        source=RecordKey(
            _row_text(row, "source_kind"),
            _row_text(row, "source_id"),
            _row_text(row, "source_version"),
        ),
        target=RecordKey(
            _row_text(row, "target_kind"),
            _row_text(row, "target_id"),
            _row_text(row, "target_version"),
        ),
        relation=_row_text(row, "relation"),
        ordinal=int(row["ordinal"]),
        created_at=_row_text(row, "created_at"),
    )


def _lifecycle_from_row(row: sqlite3.Row) -> LifecycleEvent:
    return LifecycleEvent(
        event_id=_row_text(row, "event_id"),
        entity=RecordKey(
            _row_text(row, "entity_kind"),
            _row_text(row, "entity_id"),
            _row_text(row, "entity_version"),
        ),
        from_state=_row_optional_text(row, "from_state"),
        to_state=_row_text(row, "to_state"),
        previous_event_id=_row_optional_text(row, "previous_event_id"),
        actor_id=_row_text(row, "actor_id"),
        policy_version=_row_text(row, "policy_version"),
        reason=_row_text(row, "reason"),
        occurred_at=_row_text(row, "occurred_at"),
        canonical_json=_row_text(row, "canonical_json"),
        event_sha256=_row_text(row, "event_sha256"),
    )


def _activation_from_row(row: sqlite3.Row) -> ActivationEvent:
    release_kind = _row_optional_text(row, "release_kind")
    target_pack_kind = _row_optional_text(row, "target_pack_kind")
    release = None
    target_pack = None
    if release_kind is not None:
        release = RecordKey(
            release_kind,
            _row_text(row, "release_id"),
            _row_text(row, "release_version"),
        )
    if target_pack_kind is not None:
        target_pack = RecordKey(
            target_pack_kind,
            _row_text(row, "target_pack_id"),
            _row_text(row, "target_pack_version"),
        )
    return ActivationEvent(
        event_id=_row_text(row, "event_id"),
        environment_id=_row_text(row, "environment_id"),
        action=_row_text(row, "action"),
        release=release,
        target_pack=target_pack,
        previous_event_id=_row_optional_text(row, "previous_event_id"),
        actor_id=_row_text(row, "actor_id"),
        reason=_row_text(row, "reason"),
        occurred_at=_row_text(row, "occurred_at"),
        canonical_json=_row_text(row, "canonical_json"),
        event_sha256=_row_text(row, "event_sha256"),
    )


def _fixture_from_row(row: sqlite3.Row) -> FixtureSet:
    return FixtureSet(
        fixture_set_id=_row_text(row, "fixture_set_id"),
        manifest_sha256=_row_text(row, "manifest_sha256"),
        loader_version=_row_text(row, "loader_version"),
        record_count=int(row["record_count"]),
        link_count=int(row["link_count"]),
        lifecycle_event_count=int(row["lifecycle_event_count"]),
        activation_event_count=int(row["activation_event_count"]),
        loaded_at=_row_text(row, "loaded_at"),
    )


class _SqliteRecordRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, record: StoredRecord) -> bool:
        for value, field in (
            (record.key.kind, "record kind"),
            (record.key.record_id, "record id"),
            (record.key.version, "record version"),
            (record.schema_version, "schema version"),
            (record.canonicalization_version, "canonicalization version"),
            (record.subject_id, "subject id"),
            (record.privacy_class, "privacy class"),
            (record.benchmark_role, "benchmark role"),
        ):
            _required_text(value, field)
        _validate_canonical_json(record.canonical_json, record.content_sha256, "record payload")

        existing = self.get(record.key)
        if existing is not None:
            if existing == record:
                return False
            raise RecordConflictError(f"immutable record key already exists: {record.key}")

        try:
            self._connection.execute(
                """
                INSERT INTO records (
                    record_kind, record_id, record_version, schema_version,
                    canonicalization_version, canonical_json, content_sha256, created_at,
                    subject_id, privacy_class, benchmark_role
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.key.kind,
                    record.key.record_id,
                    record.key.version,
                    record.schema_version,
                    record.canonicalization_version,
                    record.canonical_json,
                    record.content_sha256,
                    record.created_at,
                    record.subject_id,
                    record.privacy_class,
                    record.benchmark_role,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise StorageIntegrityError(f"could not store record {record.key}: {error}") from error
        return True

    def get(self, key: RecordKey) -> StoredRecord | None:
        row = self._connection.execute(
            """
            SELECT * FROM records
            WHERE record_kind = ? AND record_id = ? AND record_version = ?
            """,
            _key_values(key),
        ).fetchone()
        return None if row is None else _record_from_row(row)

    def require(self, key: RecordKey) -> StoredRecord:
        record = self.get(key)
        if record is None:
            raise RecordNotFoundError(f"exact record version not found: {key}")
        return record

    def list_versions(self, kind: str, record_id: str) -> tuple[StoredRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM records
            WHERE record_kind = ? AND record_id = ?
            ORDER BY created_at, record_version COLLATE BINARY
            """,
            (kind, record_id),
        ).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def list_records(
        self,
        *,
        kind: str | None = None,
        subject_id: str | None = None,
        benchmark_role: str | None = None,
    ) -> tuple[StoredRecord, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        for column, value in (
            ("record_kind", kind),
            ("subject_id", subject_id),
            ("benchmark_role", benchmark_role),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._connection.execute(
            "SELECT * FROM records"
            + where
            + " ORDER BY record_kind, record_id, created_at, record_version COLLATE BINARY",
            parameters,
        ).fetchall()
        return tuple(_record_from_row(row) for row in rows)


class _SqliteLinkRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, link: RecordLink) -> bool:
        if link.ordinal < 0:
            raise StorageIntegrityError("link ordinal must be non-negative")
        _required_text(link.relation, "link relation")
        existing_row = self._connection.execute(
            """
            SELECT * FROM record_links
            WHERE source_kind = ? AND source_id = ? AND source_version = ?
              AND relation = ?
              AND target_kind = ? AND target_id = ? AND target_version = ?
            """,
            (*_key_values(link.source), link.relation, *_key_values(link.target)),
        ).fetchone()
        if existing_row is not None:
            if _link_from_row(existing_row) == link:
                return False
            raise RecordConflictError("immutable record link already exists with different data")
        try:
            self._connection.execute(
                """
                INSERT INTO record_links (
                    source_kind, source_id, source_version,
                    target_kind, target_id, target_version,
                    relation, ordinal, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    *_key_values(link.source),
                    *_key_values(link.target),
                    link.relation,
                    link.ordinal,
                    link.created_at,
                ),
            )
        except sqlite3.IntegrityError as error:
            message = str(error)
            if (
                "UNIQUE constraint failed" in message
                or "frozen" in message
                or "validated" in message
            ):
                raise RecordConflictError(f"could not store immutable link: {message}") from error
            raise StorageIntegrityError(f"could not store record link: {message}") from error
        return True

    def outgoing(self, source: RecordKey, *, relation: str | None = None) -> tuple[RecordLink, ...]:
        sql = (
            "SELECT * FROM record_links "
            "WHERE source_kind = ? AND source_id = ? AND source_version = ?"
        )
        parameters: tuple[str, ...] = _key_values(source)
        if relation is not None:
            sql += " AND relation = ?"
            parameters = (*parameters, relation)
        sql += " ORDER BY relation, ordinal, target_kind, target_id, target_version"
        rows = self._connection.execute(sql, parameters).fetchall()
        return tuple(_link_from_row(row) for row in rows)

    def incoming(self, target: RecordKey, *, relation: str | None = None) -> tuple[RecordLink, ...]:
        sql = (
            "SELECT * FROM record_links "
            "WHERE target_kind = ? AND target_id = ? AND target_version = ?"
        )
        parameters: tuple[str, ...] = _key_values(target)
        if relation is not None:
            sql += " AND relation = ?"
            parameters = (*parameters, relation)
        sql += " ORDER BY relation, source_kind, source_id, source_version, ordinal"
        rows = self._connection.execute(sql, parameters).fetchall()
        return tuple(_link_from_row(row) for row in rows)


class _SqliteLifecycleRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, event: LifecycleEvent) -> bool:
        _required_text(event.event_id, "lifecycle event id")
        _required_text(event.to_state, "lifecycle target state")
        _validate_canonical_json(event.canonical_json, event.event_sha256, "lifecycle event")
        existing_row = self._connection.execute(
            "SELECT * FROM lifecycle_events WHERE event_id = ?", (event.event_id,)
        ).fetchone()
        if existing_row is not None:
            if _lifecycle_from_row(existing_row) == event:
                return False
            raise HistoryConflictError("lifecycle event id already names different content")
        try:
            self._connection.execute(
                """
                INSERT INTO lifecycle_events (
                    event_id, entity_kind, entity_id, entity_version, from_state, to_state,
                    previous_event_id, actor_id, policy_version, reason, occurred_at,
                    canonical_json, event_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    *_key_values(event.entity),
                    event.from_state,
                    event.to_state,
                    event.previous_event_id,
                    event.actor_id,
                    event.policy_version,
                    event.reason,
                    event.occurred_at,
                    event.canonical_json,
                    event.event_sha256,
                ),
            )
        except sqlite3.IntegrityError as error:
            message = str(error)
            if "current head" in message:
                raise HistoryConflictError(message) from error
            raise StorageIntegrityError(f"could not append lifecycle event: {message}") from error
        return True

    def history(self, entity: RecordKey) -> tuple[LifecycleEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM lifecycle_events
            WHERE entity_kind = ? AND entity_id = ? AND entity_version = ?
            ORDER BY sequence
            """,
            _key_values(entity),
        ).fetchall()
        return tuple(_lifecycle_from_row(row) for row in rows)

    def current_state(self, entity: RecordKey) -> str | None:
        row = self._connection.execute(
            """
            SELECT to_state FROM lifecycle_events
            WHERE entity_kind = ? AND entity_id = ? AND entity_version = ?
            ORDER BY sequence DESC LIMIT 1
            """,
            _key_values(entity),
        ).fetchone()
        return None if row is None else cast(str, row["to_state"])


class _SqliteActivationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, event: ActivationEvent, *, expected_previous_event_id: str | None) -> bool:
        _required_text(event.event_id, "activation event id")
        _required_text(event.environment_id, "activation environment id")
        _validate_canonical_json(event.canonical_json, event.event_sha256, "activation event")
        existing_row = self._connection.execute(
            "SELECT * FROM activation_events WHERE event_id = ?", (event.event_id,)
        ).fetchone()
        if existing_row is not None:
            if _activation_from_row(existing_row) == event:
                return False
            raise HistoryConflictError("activation event id already names different content")

        current = self.current(event.environment_id)
        actual_previous = None if current is None else current.event_id
        if actual_previous != expected_previous_event_id:
            raise HistoryConflictError(
                "activation head changed: "
                f"expected {expected_previous_event_id!r}, found {actual_previous!r}"
            )
        if event.previous_event_id != expected_previous_event_id:
            raise HistoryConflictError(
                "activation event previous_event_id does not match the expected head"
            )

        release_values: tuple[str | None, str | None, str | None]
        pack_values: tuple[str | None, str | None, str | None]
        release_values = (None, None, None) if event.release is None else _key_values(event.release)
        pack_values = (
            (None, None, None) if event.target_pack is None else _key_values(event.target_pack)
        )
        try:
            self._connection.execute(
                """
                INSERT INTO activation_events (
                    event_id, environment_id, action,
                    release_kind, release_id, release_version,
                    target_pack_kind, target_pack_id, target_pack_version,
                    previous_event_id, actor_id, reason, occurred_at,
                    canonical_json, event_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.environment_id,
                    event.action,
                    *release_values,
                    *pack_values,
                    event.previous_event_id,
                    event.actor_id,
                    event.reason,
                    event.occurred_at,
                    event.canonical_json,
                    event.event_sha256,
                ),
            )
        except sqlite3.IntegrityError as error:
            message = str(error)
            if "current head" in message:
                raise HistoryConflictError(message) from error
            raise StorageIntegrityError(f"could not append activation event: {message}") from error
        return True

    def current(self, environment_id: str) -> ActivationEvent | None:
        row = self._connection.execute(
            """
            SELECT * FROM activation_events
            WHERE environment_id = ? ORDER BY sequence DESC LIMIT 1
            """,
            (environment_id,),
        ).fetchone()
        return None if row is None else _activation_from_row(row)

    def list_current(self) -> tuple[ActivationEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT current.*
            FROM activation_events AS current
            WHERE current.sequence = (
                SELECT MAX(candidate.sequence)
                FROM activation_events AS candidate
                WHERE candidate.environment_id = current.environment_id
            )
            ORDER BY current.environment_id
            """
        ).fetchall()
        return tuple(_activation_from_row(row) for row in rows)

    def history(self, environment_id: str) -> tuple[ActivationEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM activation_events
            WHERE environment_id = ? ORDER BY sequence
            """,
            (environment_id,),
        ).fetchall()
        return tuple(_activation_from_row(row) for row in rows)


class _SqliteFixtureLedgerRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, fixture_set_id: str) -> FixtureSet | None:
        row = self._connection.execute(
            "SELECT * FROM fixture_sets WHERE fixture_set_id = ?", (fixture_set_id,)
        ).fetchone()
        return None if row is None else _fixture_from_row(row)

    def add(self, fixture_set: FixtureSet) -> bool:
        existing = self.get(fixture_set.fixture_set_id)
        if existing is not None:
            if existing == fixture_set:
                return False
            raise FixtureConflictError(
                f"fixture-set id already exists with another manifest: {fixture_set.fixture_set_id}"
            )
        try:
            self._connection.execute(
                """
                INSERT INTO fixture_sets (
                    fixture_set_id, manifest_sha256, loader_version, record_count, link_count,
                    lifecycle_event_count, activation_event_count, loaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fixture_set.fixture_set_id,
                    fixture_set.manifest_sha256,
                    fixture_set.loader_version,
                    fixture_set.record_count,
                    fixture_set.link_count,
                    fixture_set.lifecycle_event_count,
                    fixture_set.activation_event_count,
                    fixture_set.loaded_at,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise FixtureConflictError(f"could not record fixture set: {error}") from error
        return True


def _connect(path: Path | str, *, read_only: bool) -> sqlite3.Connection:
    memory = str(path) == ":memory:"
    if read_only and memory:
        raise ValueError("an in-memory database cannot be opened read-only")

    if memory:
        database: str = ":memory:"
        uri = False
    else:
        resolved = Path(path).expanduser().resolve()
        if read_only:
            database = f"{resolved.as_uri()}?mode=ro"
            uri = True
        else:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            database = str(resolved)
            uri = False

    connection = sqlite3.connect(
        database,
        timeout=5.0,
        isolation_level=None,
        uri=uri,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA recursive_triggers = ON")
    if not read_only:
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
    enabled = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    if enabled != 1:
        connection.close()
        raise StorageIntegrityError("SQLite foreign-key enforcement could not be enabled")
    return connection


class SqliteUnitOfWork:
    """A rollback-by-default SQLite transaction over all repositories."""

    records: RecordRepository
    links: LinkRepository
    lifecycle: LifecycleRepository
    activations: ActivationRepository
    fixture_sets: FixtureLedgerRepository

    def __init__(self, path: Path | str, *, write: bool = True) -> None:
        self._connection = _connect(path, read_only=not write)
        self._write = write
        self._entered = False
        self._finished = False
        self.records = _SqliteRecordRepository(self._connection)
        self.links = _SqliteLinkRepository(self._connection)
        self.lifecycle = _SqliteLifecycleRepository(self._connection)
        self.activations = _SqliteActivationRepository(self._connection)
        self.fixture_sets = _SqliteFixtureLedgerRepository(self._connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the connection for migration and diagnostic tests, not application queries."""

        return self._connection

    def __enter__(self) -> SqliteUnitOfWork:
        if self._entered:
            raise RuntimeError("unit of work cannot be entered twice")
        self._connection.execute("BEGIN IMMEDIATE" if self._write else "BEGIN")
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc_value, traceback
        try:
            if self._connection.in_transaction:
                self._connection.rollback()
        finally:
            self._connection.close()

    def commit(self) -> None:
        if not self._entered or self._finished:
            raise RuntimeError("unit of work is not an active transaction")
        self._connection.commit()
        self._finished = True

    def rollback(self) -> None:
        if not self._entered or self._finished:
            raise RuntimeError("unit of work is not an active transaction")
        self._connection.rollback()
        self._finished = True


class SqliteUnitOfWorkFactory:
    """Initialize a ledger and create isolated SQLite units of work."""

    def __init__(self, path: Path | str) -> None:
        self.path = path

    def initialize(self, runner: MigrationRunner | None = None) -> int:
        """Create or migrate the ledger and return its database schema version."""

        connection = _connect(self.path, read_only=False)
        try:
            return (runner or MigrationRunner()).migrate(connection)
        finally:
            connection.close()

    def __call__(self, *, write: bool = True) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(self.path, write=write)
