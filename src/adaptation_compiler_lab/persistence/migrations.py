"""Small, checksum-verified, numbered SQLite migration runner."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
from typing import Final

from adaptation_compiler_lab.persistence.errors import (
    DatabaseVersionError,
    MigrationDriftError,
    MigrationError,
    MigrationSequenceError,
)

_MIGRATION_PATTERN: Final = re.compile(r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")
_RUNNER_VERSION: Final = "1"
_MIGRATION_PACKAGE: Final = "adaptation_compiler_lab.persistence.sql"


@dataclass(frozen=True, order=True, slots=True)
class Migration:
    """One immutable migration source file."""

    version: int
    name: str
    sql: str
    checksum_sha256: str

    @classmethod
    def from_sql(cls, version: int, name: str, sql: str) -> Migration:
        """Construct a migration and calculate its source checksum."""

        return cls(
            version=version,
            name=name,
            sql=sql,
            checksum_sha256=sha256(sql.encode("utf-8")).hexdigest(),
        )


class MigrationRunner:
    """Apply bundled migrations exactly once and detect source drift."""

    def __init__(self, migrations: Iterable[Migration] | None = None) -> None:
        discovered = tuple(migrations) if migrations is not None else self._discover()
        self._migrations = tuple(sorted(discovered, key=lambda migration: migration.version))
        self._validate_sequence(self._migrations)

    @property
    def latest_version(self) -> int:
        """Return the latest migration version known to this runner."""

        return self._migrations[-1].version if self._migrations else 0

    def migrate(self, connection: sqlite3.Connection) -> int:
        """Upgrade ``connection`` and return its resulting schema version."""

        self._bootstrap_ledger(connection)
        applied = self._applied(connection)
        available = {migration.version: migration for migration in self._migrations}

        unknown_versions = sorted(set(applied) - set(available))
        if unknown_versions:
            rendered = ", ".join(str(version) for version in unknown_versions)
            raise DatabaseVersionError(
                f"database contains migration versions not bundled by this application: {rendered}"
            )

        for version, (name, checksum) in applied.items():
            migration = available[version]
            if migration.name != name or migration.checksum_sha256 != checksum:
                raise MigrationDriftError(
                    f"applied migration {version:04d}_{name} does not match bundled source"
                )

        for migration in self._migrations:
            if migration.version not in applied:
                self._apply(connection, migration)

        return self.latest_version

    @staticmethod
    def _discover() -> tuple[Migration, ...]:
        root = resources.files(_MIGRATION_PACKAGE)
        migrations: list[Migration] = []
        for resource in root.iterdir():
            match = _MIGRATION_PATTERN.fullmatch(resource.name)
            if match is None:
                continue
            sql = resource.read_text(encoding="utf-8")
            migrations.append(
                Migration.from_sql(
                    version=int(match.group("version")),
                    name=match.group("name"),
                    sql=sql,
                )
            )
        return tuple(migrations)

    @staticmethod
    def _validate_sequence(migrations: tuple[Migration, ...]) -> None:
        versions = [migration.version for migration in migrations]
        if len(versions) != len(set(versions)):
            raise MigrationSequenceError("migration versions must be unique")
        expected = list(range(1, len(versions) + 1))
        if versions != expected:
            raise MigrationSequenceError(
                f"migration versions must be contiguous from 1; found {versions}"
            )
        for migration in migrations:
            if (
                not migration.name
                or _MIGRATION_PATTERN.fullmatch(f"{migration.version:04d}_{migration.name}.sql")
                is None
            ):
                raise MigrationSequenceError(f"invalid migration name: {migration.name!r}")

    @staticmethod
    def _bootstrap_ledger(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY CHECK (version > 0),
                name TEXT NOT NULL,
                checksum_sha256 TEXT NOT NULL CHECK (length(checksum_sha256) = 64),
                applied_at TEXT NOT NULL,
                runner_version TEXT NOT NULL
            ) STRICT
            """
        )

    @staticmethod
    def _applied(connection: sqlite3.Connection) -> dict[int, tuple[str, str]]:
        rows = connection.execute(
            "SELECT version, name, checksum_sha256 FROM schema_migrations ORDER BY version"
        ).fetchall()
        return {int(row[0]): (str(row[1]), str(row[2])) for row in rows}

    @staticmethod
    def _sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _apply(self, connection: sqlite3.Connection, migration: Migration) -> None:
        applied_at = datetime.now(UTC).isoformat()
        ledger_insert = (
            "INSERT INTO schema_migrations "
            "(version, name, checksum_sha256, applied_at, runner_version) VALUES ("
            f"{migration.version}, "
            f"{self._sql_literal(migration.name)}, "
            f"{self._sql_literal(migration.checksum_sha256)}, "
            f"{self._sql_literal(applied_at)}, "
            f"{self._sql_literal(_RUNNER_VERSION)});"
        )
        script = (
            "BEGIN IMMEDIATE;\n"
            f"{migration.sql.rstrip()}\n"
            f"{ledger_insert}\n"
            f"PRAGMA user_version = {migration.version};\n"
            "COMMIT;"
        )
        try:
            connection.executescript(script)
        except sqlite3.Error as error:
            if connection.in_transaction:
                connection.rollback()
            raise MigrationError(
                f"failed to apply migration {migration.version:04d}_{migration.name}: {error}"
            ) from error
