"""Migration ordering, drift, and atomicity tests."""

import sqlite3
from pathlib import Path

import pytest

from adaptation_compiler_lab.persistence.errors import (
    MigrationDriftError,
    MigrationError,
    MigrationSequenceError,
)
from adaptation_compiler_lab.persistence.migrations import Migration, MigrationRunner
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory


def test_bundled_migrations_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    factory = SqliteUnitOfWorkFactory(path)

    first = factory.initialize()
    second = factory.initialize()

    assert first == second == 2
    with sqlite3.connect(path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == 2


def test_applied_migration_checksum_drift_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "drift.sqlite3"
    original = Migration.from_sql(1, "example", "CREATE TABLE example (id INTEGER);")
    changed = Migration.from_sql(1, "example", "CREATE TABLE example (id TEXT);")
    factory = SqliteUnitOfWorkFactory(path)
    factory.initialize(MigrationRunner([original]))

    with pytest.raises(MigrationDriftError):
        factory.initialize(MigrationRunner([changed]))


def test_migration_sequence_must_be_contiguous() -> None:
    with pytest.raises(MigrationSequenceError):
        MigrationRunner([Migration.from_sql(2, "late", "SELECT 1;")])


def test_failed_migration_rolls_back_its_partial_schema(tmp_path: Path) -> None:
    path = tmp_path / "atomic.sqlite3"
    broken = Migration.from_sql(
        1,
        "broken",
        "CREATE TABLE should_rollback (id INTEGER);\nTHIS IS NOT SQL;",
    )

    with pytest.raises(MigrationError):
        SqliteUnitOfWorkFactory(path).initialize(MigrationRunner([broken]))

    with sqlite3.connect(path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'should_rollback'"
        ).fetchone()
        applied = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert table is None
    assert applied == 0
