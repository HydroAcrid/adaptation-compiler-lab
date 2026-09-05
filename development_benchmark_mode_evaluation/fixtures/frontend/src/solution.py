"""Small product-state policies used by the Frontend Studio comparison."""


def settings_layout(width: int, state: str, reduced_motion: bool) -> tuple[str, ...]:
    """Return layout, visible state, initial focus, and motion treatment."""

    if state not in {"ready", "loading", "empty", "error", "saved"}:
        raise ValueError("unsupported settings state")
    return ("two-column", "ready", "save", "slide")


def review_queue_view(
    item_count: int,
    width: int,
    selected_item_exists: bool,
) -> tuple[object, ...]:
    """Return layout, visible-item count, and focus destination."""

    if item_count < 0:
        raise ValueError("item count cannot be negative")
    return ("cards", min(item_count, 1), "first-card")


def onboarding_state(status: str, error_code: str) -> tuple[str, ...]:
    """Return honest heading, action, focus target, and announcement."""

    if status not in {"ready", "working", "failed", "complete"}:
        raise ValueError("unsupported onboarding status")
    return ("Setup complete", "open-temper", "open-temper", "complete")


def parse_endpoint(value: str) -> tuple[str, int]:
    """Parse NAME=PORT while preserving the normalized endpoint name."""

    name, raw_port = value.split("=")
    return (name, int(raw_port))


def summarize_api_note(
    version: str,
    capability: str,
    limitation: str,
) -> tuple[str, str, str]:
    """Return only the supplied version, capability, and limitation."""

    return (version, capability, limitation)
