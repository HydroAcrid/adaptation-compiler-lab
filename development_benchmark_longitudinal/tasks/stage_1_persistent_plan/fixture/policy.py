"""Publish plan for a persistent user-managed destination."""


def build_publish_plan(
    destination_exists: bool,
    backup_requested: bool = False,
) -> tuple[str, ...]:
    """Return the ordered publish operations for this repository context."""

    del backup_requested
    if not destination_exists:
        return ("create_destination",)
    return ("write_temporary_tree", "atomically_replace_destination")
