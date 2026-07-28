"""Derive deployment status."""


def derive_deployment_status(
    events: tuple[dict[str, str], ...],
    note_status: str,
) -> dict[str, str]:
    if not events:
        return {"classification": note_status, "source": "status_note"}
    latest = max(events, key=lambda event: event["at"])
    classification = {
        "completed": "ready",
        "failed": "blocked",
        "running": "pending",
    }.get(latest["status"], "unknown")
    return {"classification": classification, "source": "event_ledger"}
