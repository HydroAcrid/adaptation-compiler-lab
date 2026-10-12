from __future__ import annotations

import json

import pytest

from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from scripts.replay_owner_habit_evaluation import equivalent_cases, migrated_wire


def test_replay_cannot_change_messages_labels_dates_or_scope() -> None:
    source = {
        "synthetic": True,
        "cases": [{"id": "fictional", "expected": ["concise"], "message": "brief"}],
    }
    target = {**source, "evaluation_version": "new"}
    assert equivalent_cases(source, target)
    target = {**source, "cases": [{"id": "fictional", "expected": [], "message": "brief"}]}
    assert not equivalent_cases(source, target)


def test_wire_migration_changes_only_the_explicit_version_stamp() -> None:
    source = {"evaluation_version": "old", "candidates": [], "known_habit_assessments": []}
    migrated = json.loads(
        migrated_wire(json.dumps(source).encode(), source_version="old", target_version="new")
    )
    assert migrated == {**source, "evaluation_version": "new"}
    with pytest.raises(AutonomyIntegrityError, match="version"):
        migrated_wire(json.dumps(source).encode(), source_version="different", target_version="new")
