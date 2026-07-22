"""Activation-pointer event and rollback tests."""

import pytest

from adaptation_compiler_lab.persistence.errors import HistoryConflictError
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

from ._helpers import make_activation, make_record


def test_activation_rollback_and_deactivation_preserve_history(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    release_one = make_record("release", "release-1")
    pack_one = make_record("target_pack", "pack-1")
    release_two = make_record("release", "release-2")
    pack_two = make_record("target_pack", "pack-2")
    activate_one = make_activation(
        "activation-1", "activate", release=release_one.key, target_pack=pack_one.key
    )
    activate_two = make_activation(
        "activation-2",
        "activate",
        release=release_two.key,
        target_pack=pack_two.key,
        previous=activate_one.event_id,
    )
    rollback = make_activation(
        "activation-3",
        "rollback",
        release=release_one.key,
        target_pack=pack_one.key,
        previous=activate_two.event_id,
    )
    deactivate = make_activation(
        "activation-4",
        "deactivate",
        release=None,
        target_pack=None,
        previous=rollback.event_id,
    )
    with database_factory() as unit_of_work:
        for record in (release_one, pack_one, release_two, pack_two):
            unit_of_work.records.add(record)
        for event, expected in (
            (activate_one, None),
            (activate_two, activate_one.event_id),
            (rollback, activate_two.event_id),
            (deactivate, rollback.event_id),
        ):
            unit_of_work.activations.append(event, expected_previous_event_id=expected)
        unit_of_work.commit()

    with database_factory(write=False) as unit_of_work:
        assert unit_of_work.activations.current("local-dev") == deactivate
        assert unit_of_work.activations.history("local-dev") == (
            activate_one,
            activate_two,
            rollback,
            deactivate,
        )


def test_activation_uses_optimistic_expected_head(
    database_factory: SqliteUnitOfWorkFactory,
) -> None:
    release = make_record("release", "release-1")
    pack = make_record("target_pack", "pack-1")
    event = make_activation("activation-1", "activate", release=release.key, target_pack=pack.key)
    stale = make_activation(
        "activation-2",
        "rollback",
        release=release.key,
        target_pack=pack.key,
        previous=event.event_id,
    )
    with database_factory() as unit_of_work:
        unit_of_work.records.add(release)
        unit_of_work.records.add(pack)
        unit_of_work.activations.append(event, expected_previous_event_id=None)
        with pytest.raises(HistoryConflictError, match="head changed"):
            unit_of_work.activations.append(stale, expected_previous_event_id=None)
