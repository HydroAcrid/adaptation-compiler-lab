"""Shared conservative model-session accounting for learning and private validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from adaptation_compiler_lab.autonomy.defaults import (
    MAX_DAILY_ANALYSES,
    MIN_REMAINING_CAPACITY,
    POLL_MINUTES,
)


def background_budget_available(
    events: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    remaining_percent: float | None,
    sessions: int = 1,
) -> bool:
    if (
        type(sessions) is not int
        or not 1 <= sessions <= MAX_DAILY_ANALYSES
        or remaining_percent is None
        or not MIN_REMAINING_CAPACITY <= remaining_percent <= 100
        or now.tzinfo is None
    ):
        return False
    analysis = [event["payload"] for event in events if event["type"] == "analysis"]
    used = 0
    starts = []
    for payload in analysis:
        try:
            started = datetime.fromisoformat(payload["started_at"])
            count = payload.get("sessions", 1)
            if (
                started.tzinfo is None
                or type(count) is not int
                or not 1 <= count <= MAX_DAILY_ANALYSES
            ):
                return False
        except (TypeError, ValueError, KeyError):
            return False
        starts.append(started)
        if started > now - timedelta(days=1):
            used += count
    return used + sessions <= MAX_DAILY_ANALYSES and (
        not starts or max(starts) <= now - timedelta(minutes=POLL_MINUTES)
    )
