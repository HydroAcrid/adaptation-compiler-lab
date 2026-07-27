"""Publish plan for a disposable generated-cache destination."""


def build_publish_plan(
    destination_exists: bool,
    backup_requested: bool = False,
) -> tuple[str, ...]:
    """Return the ordered publish operations for this repository context."""

    if not destination_exists:
        return ("create_destination",)
    if backup_requested:
        return ("create_recoverable_backup", "replace_destination")
    return ("refuse_overwrite",)
