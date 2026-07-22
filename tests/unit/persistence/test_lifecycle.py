"""Append-only lifecycle history tests."""

import sqlite3

import pytest

from adaptation_compiler_lab.persistence.errors import HistoryConflictError
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

from ._helpers import make_lifecycle, make_record


def test_lifecycle_history_is_ordered_and_chained(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    artifact = make_record("artifact", "artifact-1")
    drafted = make_lifecycle("event-draft", artifact.key, "draft")
    approved = make_lifecycle(
        "event-approved",
        artifact.key,
        "approved",
        previous=drafted.event_id,
        from_state="draft",
    )
    with database_factory() as unit_of_work:
        unit_of_work.records.add(artifact)
        unit_of_work.lifecycle.append(drafted)
        unit_of_work.lifecycle.append(approved)
        unit_of_work.commit()

    with database_factory(write=False) as unit_of_work:
        assert unit_of_work.lifecycle.history(artifact.key) == (drafted, approved)
        assert unit_of_work.lifecycle.current_state(artifact.key) == "approved"


def test_lifecycle_fork_is_rejected(database_factory: SqliteUnitOfWorkFactory) -> None:
    artifact = make_record("artifact", "artifact-1")
    first = make_lifecycle("event-first", artifact.key, "draft")
    second = make_lifecycle("event-second", artifact.key, "evaluated", previous=first.event_id)
    fork = make_lifecycle("event-fork", artifact.key, "rejected", previous=first.event_id)
    with database_factory() as unit_of_work:
        unit_of_work.records.add(artifact)
        unit_of_work.lifecycle.append(first)
        unit_of_work.lifecycle.append(second)
        with pytest.raises(HistoryConflictError):
            unit_of_work.lifecycle.append(fork)


def test_record_and_event_rows_reject_sql_update_and_delete(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    artifact = make_record("artifact", "artifact-1")
    event = make_lifecycle("event-first", artifact.key, "draft")
    with database_factory() as unit_of_work:
        unit_of_work.records.add(artifact)
        unit_of_work.lifecycle.append(event)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            unit_of_work.connection.execute(
                "UPDATE records SET privacy_class = 'public' WHERE record_id = 'artifact-1'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            unit_of_work.connection.execute(
                "DELETE FROM lifecycle_events WHERE event_id = 'event-first'"
            )
