from __future__ import annotations

from collections import Counter
from typing import Any, cast

from scripts.prepare_habit_prospective import build as previous
from scripts.prepare_habit_prospective_v11 import build as fresh


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
