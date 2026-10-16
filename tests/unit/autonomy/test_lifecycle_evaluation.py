from __future__ import annotations

import pytest

from adaptation_compiler_lab.autonomy.lifecycle_evaluation import affected_habits_paused

TARGET = frozenset({("observed-project", "summary", "concise_summary")})
OLD: dict[str, object] = {
    "project_id": "observed-project",
    "task_class": "summary",
    "style_key": "concise_summary",
    "state": "paused",
}
NEW: dict[str, object] = {**OLD, "style_key": "explain_reasoning", "state": "provisional"}


def test_a_new_unserved_hypothesis_does_not_disguise_an_old_habit_pausing() -> None:
    assert affected_habits_paused([OLD, NEW], TARGET)


@pytest.mark.parametrize(
    "change",
    [
        {"state": "active"},
        {"state": "trial"},
        {"project_id": "unrelated-project"},
        {"task_class": "progress_update"},
        {"style_key": "outcome_first"},
    ],
)
def test_a_missing_wrong_scope_or_unpaused_target_cannot_pass(change: dict[str, str]) -> None:
    assert not affected_habits_paused([{**OLD, **change}, NEW], TARGET)


def test_duplicate_targets_or_an_empty_target_set_cannot_pass() -> None:
    assert not affected_habits_paused([OLD, OLD], TARGET)
    assert not affected_habits_paused([], frozenset())
