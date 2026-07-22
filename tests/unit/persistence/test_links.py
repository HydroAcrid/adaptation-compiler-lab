"""Exact-version relationship and frozen-membership tests."""

import pytest

from adaptation_compiler_lab.persistence.errors import IntegrityError, RecordConflictError
from adaptation_compiler_lab.persistence.records import RecordLink
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

from ._helpers import STAMP, make_lifecycle, make_record


def test_links_are_traversable_in_both_directions(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    artifact = make_record("artifact", "artifact-1")
    evidence = make_record("evidence", "evidence-1")
    link = RecordLink(artifact.key, evidence.key, "supports", 0, STAMP)
    with database_factory() as unit_of_work:
        unit_of_work.records.add(evidence)
        unit_of_work.records.add(artifact)
        assert unit_of_work.links.add(link)
        assert not unit_of_work.links.add(link)
        unit_of_work.commit()

    with database_factory(write=False) as unit_of_work:
        assert unit_of_work.links.outgoing(artifact.key) == (link,)
        assert unit_of_work.links.incoming(evidence.key) == (link,)


def test_link_to_missing_exact_version_is_rejected(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    artifact = make_record("artifact", "artifact-1")
    evidence = make_record("evidence", "missing")
    with database_factory() as unit_of_work:
        unit_of_work.records.add(artifact)
        with pytest.raises(IntegrityError):
            unit_of_work.links.add(RecordLink(artifact.key, evidence.key, "supports", 0, STAMP))


def test_release_membership_cannot_change_after_release_freeze(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    release = make_record("release", "release-1")
    first = make_record("artifact", "artifact-1")
    second = make_record("artifact", "artifact-2")
    with database_factory() as unit_of_work:
        for record in (release, first, second):
            unit_of_work.records.add(record)
        unit_of_work.links.add(RecordLink(release.key, first.key, "contains_artifact", 0, STAMP))
        unit_of_work.lifecycle.append(make_lifecycle("freeze-release", release.key, "released"))
        with pytest.raises(RecordConflictError):
            unit_of_work.links.add(
                RecordLink(release.key, second.key, "contains_artifact", 1, STAMP)
            )
