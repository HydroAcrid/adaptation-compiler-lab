"""Evaluate explicitly named lifecycle targets without conflating replacement hypotheses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

ScopeKey = tuple[str, str, str]


def affected_habits_paused(
    hypotheses: Sequence[Mapping[str, object]], targets: frozenset[ScopeKey]
) -> bool:
    """Every named old habit must exist once, in its exact scope, and be paused."""
    if not targets:
        return False
    matched: dict[ScopeKey, str] = {}
    for value in hypotheses:
        project, task, style = (
            value.get("project_id"),
            value.get("task_class"),
            value.get("style_key"),
        )
        if not all(isinstance(item, str) for item in (project, task, style)):
            continue
        assert isinstance(project, str) and isinstance(task, str) and isinstance(style, str)
        key = project, task, style
        if key not in targets:
            continue
        state = value.get("state")
        if key in matched or not isinstance(state, str):
            return False
        matched[key] = state
    return matched.keys() == targets and all(state == "paused" for state in matched.values())
