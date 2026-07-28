"""Derive deployment state from a public status contract."""

EVENT_CLASSIFICATIONS = {
    "completed": "ready",
    "failed": "blocked",
    "running": "active",
}
LIVE_SOURCE = "event_ledger"


def derive_status(
    events: tuple[dict[str, str], ...],
    note_status: str,
) -> dict[str, str]:
    if not events:
        return {"classification": note_status, "source": "status_note"}
    latest = max(events, key=lambda event: event["at"])
    return {
        "classification": EVENT_CLASSIFICATIONS[latest["status"]],
        "source": LIVE_SOURCE,
    }
