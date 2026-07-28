"""Derive current deployment state from live observations."""

STATE_BY_EVENT = {
    "completed": "ready",
    "failed": "blocked",
    "running": "in_progress",
}
LIVE_SOURCE = "deployment_events"
NOTE_SOURCE = "status_note"


def derive_deployment_state(
    events: tuple[dict[str, str], ...],
    note_state: str,
) -> dict[str, str]:
    return {"state": note_state, "source": NOTE_SOURCE}
