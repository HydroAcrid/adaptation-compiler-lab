"""Migration ordering, drift, and atomicity tests."""

import sqlite3
from importlib import resources
from pathlib import Path

import pytest

from adaptation_compiler_lab.governance import GovernanceObjectKind
from adaptation_compiler_lab.persistence.errors import (
    MigrationDriftError,
    MigrationError,
    MigrationSequenceError,
)
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.migrations import Migration, MigrationRunner
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from tests.unit.test_governance import _consent, _identity, _recall_event


def test_bundled_migrations_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    factory = SqliteUnitOfWorkFactory(path)

    first = factory.initialize()
    second = factory.initialize()

    assert first == second == 9
    with sqlite3.connect(path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == 9


def test_governance_ledger_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(governance_objects)")}
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'governance_%'"
            )
        }

    assert {"canonical_json", "content_sha256", "signature_base64"}.issubset(columns)
    assert triggers == {"governance_objects_reject_delete", "governance_objects_reject_update"}


def test_existing_v2_ledger_upgrades_without_rewriting_records(tmp_path: Path) -> None:
    root = resources.files("adaptation_compiler_lab.persistence.sql")
    legacy = []
    for version, filename, name in (
        (1, "0001_record_ledger.sql", "record_ledger"),
        (2, "0002_append_only_guards.sql", "append_only_guards"),
    ):
        legacy.append(
            Migration.from_sql(version, name, (root / filename).read_text(encoding="utf-8"))
        )
    path = tmp_path / "legacy.sqlite3"
    factory = SqliteUnitOfWorkFactory(path)
    assert factory.initialize(MigrationRunner(legacy)) == 2
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO records VALUES (
                'evidence', 'legacy-synthetic', '1.0.0', '1.0', '1.0.0', '{}',
                ?, '2026-01-01T00:00:00+00:00', 'synthetic-user', 'internal', 'synthetic'
            )
            """,
            ("0" * 64,),
        )
        connection.commit()

    assert factory.initialize() == 9
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT record_id, schema_version FROM records WHERE record_id = 'legacy-synthetic'"
        ).fetchone()
    assert row == ("legacy-synthetic", "1.0")


def test_existing_v3_governance_objects_survive_recall_migration(tmp_path: Path) -> None:
    root = resources.files("adaptation_compiler_lab.persistence.sql")
    legacy = tuple(
        Migration.from_sql(
            version,
            name,
            (root / filename).read_text(encoding="utf-8"),
        )
        for version, filename, name in (
            (1, "0001_record_ledger.sql", "record_ledger"),
            (2, "0002_append_only_guards.sql", "append_only_guards"),
            (3, "0003_governance_ledger.sql", "governance_ledger"),
        )
    )
    path = tmp_path / "v3-governance.sqlite3"
    factory = SqliteUnitOfWorkFactory(path)
    assert factory.initialize(MigrationRunner(legacy)) == 3
    _, identity = _identity()
    ledger = GovernanceLedger(path, subject_id="kevin")
    assert ledger.add(identity)

    assert factory.initialize() == 9
    assert ledger.get(GovernanceObjectKind.SIGNER_IDENTITY, identity.identity_id) == identity


def test_existing_v4_recall_objects_survive_benchmark_registry_migration(tmp_path: Path) -> None:
    root = resources.files("adaptation_compiler_lab.persistence.sql")
    legacy = tuple(
        Migration.from_sql(
            version,
            name,
            (root / filename).read_text(encoding="utf-8"),
        )
        for version, filename, name in (
            (1, "0001_record_ledger.sql", "record_ledger"),
            (2, "0002_append_only_guards.sql", "append_only_guards"),
            (3, "0003_governance_ledger.sql", "governance_ledger"),
            (4, "0004_recall_governance.sql", "recall_governance"),
        )
    )
    path = tmp_path / "v4-recall.sqlite3"
    factory = SqliteUnitOfWorkFactory(path)
    assert factory.initialize(MigrationRunner(legacy)) == 4
    signer, identity = _identity()
    consent = _consent(signer)
    impact, _ = _recall_event(signer, consent)
    ledger = GovernanceLedger(path, subject_id="kevin")
    assert ledger.add(identity)
    assert ledger.add(consent)
    assert ledger.add(impact)

    assert factory.initialize() == 9
    assert ledger.get(GovernanceObjectKind.DEPENDENCY_IMPACT, impact.impact_id) == impact


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


def test_dogfood_feedback_table_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "dogfood.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(dogfood_feedback)")}
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'dogfood_feedback_%'"
            )
        }

    assert {
        "canonical_json",
        "content_sha256",
        "feedback_id",
        "outcome",
        "stage",
        "subject_id",
    } <= columns
    assert triggers == {
        "dogfood_feedback_reject_delete",
        "dogfood_feedback_reject_update",
    }


def test_automatic_runtime_tables_are_append_only(tmp_path: Path) -> None:
    path = tmp_path / "automatic-runtime.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()

    with sqlite3.connect(path) as connection:
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'automatic_runtime_%'"
            )
        }

        assert triggers == {
            "automatic_runtime_activation_events_reject_delete",
            "automatic_runtime_activation_events_reject_update",
            "automatic_runtime_activation_feedback_reject_delete",
            "automatic_runtime_activation_feedback_reject_update",
            "automatic_runtime_cycles_reject_delete",
            "automatic_runtime_cycles_reject_update",
            "automatic_runtime_delivery_acknowledgements_reject_delete",
            "automatic_runtime_delivery_acknowledgements_reject_update",
            "automatic_runtime_feedback_reject_delete",
            "automatic_runtime_feedback_reject_update",
            "automatic_runtime_governance_events_reject_delete",
            "automatic_runtime_governance_events_reject_update",
            "automatic_runtime_learning_cycles_reject_delete",
            "automatic_runtime_learning_cycles_reject_update",
            "automatic_runtime_learning_events_reject_delete",
            "automatic_runtime_learning_events_reject_update",
            "automatic_runtime_learning_assessments_reject_delete",
            "automatic_runtime_learning_assessments_reject_update",
            "automatic_runtime_learning_review_queue_reject_delete",
            "automatic_runtime_learning_review_queue_reject_update",
            "automatic_runtime_review_queue_reject_delete",
            "automatic_runtime_review_queue_reject_update",
            "automatic_runtime_source_checkpoints_reject_delete",
            "automatic_runtime_source_checkpoints_reject_update",
            "automatic_runtime_states_reject_delete",
            "automatic_runtime_states_reject_update",
            "automatic_runtime_task_activations_reject_delete",
            "automatic_runtime_task_activations_reject_update",
        }
