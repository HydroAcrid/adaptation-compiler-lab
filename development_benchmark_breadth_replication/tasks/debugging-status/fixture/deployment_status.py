"""Derive deployment status."""


def derive_deployment_status(
    events: tuple[dict[str, str], ...],
    note_status: str,
) -> dict[str, str]:
    return {"classification": note_status, "source": "status_note"}
