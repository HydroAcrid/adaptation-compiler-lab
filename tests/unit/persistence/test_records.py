"""Immutable record repository tests."""

from dataclasses import replace

import pytest

from adaptation_compiler_lab.persistence.errors import (
    IntegrityError,
    RecordConflictError,
    RecordNotFoundError,
)
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

from ._helpers import make_record


@pytest.mark.parametrize(
    "kind",
    [
        "task_record",
        "outcome",
        "evidence",
        "evaluation_case",
        "lesson_candidate",
        "artifact",
        "release",
        "target_pack",
    ],
)
def test_all_domain_record_kinds_round_trip(
    database_factory: SqliteUnitOfWorkFactory, kind: str
) -> None:
    record = make_record(kind, f"{kind}-1")
    with database_factory() as unit_of_work:
        assert unit_of_work.records.add(record)
        assert not unit_of_work.records.add(record)
        unit_of_work.commit()

    with database_factory(write=False) as unit_of_work:
        assert unit_of_work.records.require(record.key) == record


def test_same_immutable_key_with_other_content_is_rejected(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    original = make_record("artifact", "artifact-1", value="first")
    conflict = make_record("artifact", "artifact-1", value="second")
    with database_factory() as unit_of_work:
        unit_of_work.records.add(original)
        with pytest.raises(RecordConflictError):
            unit_of_work.records.add(conflict)


def test_digest_mismatch_is_rejected(database_factory: SqliteUnitOfWorkFactory) -> None:
    record = make_record("evidence", "evidence-1")
    invalid = replace(record, content_sha256="0" * 64)
    with database_factory() as unit_of_work, pytest.raises(IntegrityError):
        unit_of_work.records.add(invalid)


def test_rollback_by_default_leaves_no_record(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    record = make_record("task_record", "task-rollback")
    with database_factory() as unit_of_work:
        unit_of_work.records.add(record)

    with database_factory(write=False) as unit_of_work, pytest.raises(RecordNotFoundError):
        unit_of_work.records.require(RecordKey("task_record", "task-rollback", "1"))


def test_record_queries_can_filter_subject_and_benchmark_role(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    construction = make_record("evidence", "construction")
    held_out = make_record("evidence", "held-out", benchmark_role="held_out")
    with database_factory() as unit_of_work:
        unit_of_work.records.add(construction)
        unit_of_work.records.add(held_out)
        unit_of_work.commit()

    with database_factory(write=False) as unit_of_work:
        assert unit_of_work.records.list_records(
            subject_id="subject-kevin", benchmark_role="construction"
        ) == (construction,)
