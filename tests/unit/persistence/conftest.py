"""Shared temporary-database fixtures for persistence tests."""

from pathlib import Path

import pytest

from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory


@pytest.fixture
def database_factory(tmp_path: Path) -> SqliteUnitOfWorkFactory:
    """Return a newly migrated, test-local SQLite ledger."""

    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    return factory
