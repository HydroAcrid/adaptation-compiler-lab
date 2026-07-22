"""Deterministic fixture transaction tests."""

from dataclasses import replace

import pytest

from adaptation_compiler_lab.persistence.errors import FixtureConflictError, IntegrityError
from adaptation_compiler_lab.persistence.fixtures import FixtureBundle, FixtureLoader
from adaptation_compiler_lab.persistence.ports import UnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import RecordLink
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

from ._helpers import STAMP, make_record


def test_fixture_load_is_deterministic_and_idempotent(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    task = make_record("task_record", "task-1")
    evidence = make_record("evidence", "evidence-1")
    bundle = FixtureBundle(
        fixture_set_id="synthetic-v1",
        loaded_at=STAMP,
        records=(evidence, task),
        links=(RecordLink(evidence.key, task.key, "observed_in", 0, STAMP),),
    )
    factory_port: UnitOfWorkFactory = database_factory
    loader = FixtureLoader(factory_port)

    first = loader.load(bundle)
    second = loader.load(bundle)

    assert not first.already_loaded
    assert second.already_loaded
    assert first.manifest_sha256 == second.manifest_sha256
    with database_factory(write=False) as unit_of_work:
        assert unit_of_work.records.list_records() == (evidence, task)


def test_fixture_identifier_reuse_with_other_content_fails(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    bundle = FixtureBundle(
        fixture_set_id="synthetic-v1",
        loaded_at=STAMP,
        records=(make_record("task_record", "task-1"),),
    )
    loader = FixtureLoader(database_factory)
    loader.load(bundle)

    with pytest.raises(FixtureConflictError):
        loader.load(replace(bundle, records=(make_record("task_record", "task-2"),)))


def test_fixture_failure_rolls_back_all_records(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    task = make_record("task_record", "task-1")
    missing = make_record("evidence", "not-in-bundle")
    bundle = FixtureBundle(
        fixture_set_id="invalid-v1",
        loaded_at=STAMP,
        records=(task,),
        links=(RecordLink(task.key, missing.key, "missing", 0, STAMP),),
    )

    with pytest.raises(IntegrityError):
        FixtureLoader(database_factory).load(bundle)

    with database_factory(write=False) as unit_of_work:
        assert unit_of_work.records.list_records() == ()
        assert unit_of_work.fixture_sets.get("invalid-v1") is None
