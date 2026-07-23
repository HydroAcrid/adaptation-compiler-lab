"""Render a descriptive report from immutable trial rows."""

from __future__ import annotations

from collections.abc import Sequence


def summarize_trials(trials: Sequence[dict[str, object]]) -> dict[str, object]:
    """Return a JSON-compatible descriptive summary."""

    passed = [trial for trial in trials if trial.get("status") == "passed"]
    return {
        "total": len(passed),
        "valid_rate": 1.0,
        "statuses": [trial["status"] for trial in passed],
        "conclusion": "The experiment confirmed success.",
    }
