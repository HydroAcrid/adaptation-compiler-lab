from __future__ import annotations

from collections import Counter
from typing import Any, cast

from scripts.prepare_habit_prospective import build as previous
from scripts.prepare_habit_prospective_v11 import build as fresh
from scripts.prepare_habit_prospective_v12 import build as opaque


def messages(data: dict[str, object]) -> set[str]:
    return {
        message
        for case in cast(list[dict[str, Any]], data["cases"])
        for episode in case["episodes"]
        for message in episode["user_messages"]
    }


def test_new_materials_preserve_cohorts_without_reusing_old_messages_or_mutating_the_builder() -> (
    None
):
    old = previous()
    new = fresh()
    assert previous() == old
    assert not (messages(old) & messages(new))
    assert Counter(case["group"] for case in cast(list[dict[str, Any]], new["cases"])) == {
        "stable": 30,
        "context_constraint": 20,
        "untrusted": 20,
        "changing": 20,
        "sparse": 15,
        "scope_override": 15,
    }


def test_model_visible_identifiers_are_opaque_without_changing_fresh_messages_or_labels() -> None:
    before, after = fresh(), opaque()
    assert messages(before) == messages(after)
    old_cases = cast(list[dict[str, Any]], before["cases"])
    new_cases = cast(list[dict[str, Any]], after["cases"])
    identifiers = []
    cohorts = {case["group"] for case in new_cases}
    for old, new in zip(old_cases, new_cases, strict=True):
        assert old["expected"] == new["expected"]
        assert old.get("control") == new.get("control")
        for episode in new["episodes"]:
            identifier = episode["task_id"]
            assert identifier.startswith("episode-") and len(identifier) == 32
            assert not any(group in identifier for group in cohorts)
            identifiers.append(identifier)
    assert len(identifiers) == len(set(identifiers))
