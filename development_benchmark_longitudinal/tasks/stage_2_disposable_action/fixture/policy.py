"""Publish policy for a disposable generated-cache destination."""


def choose_publish_action(
    destination_exists: bool,
    backup_requested: bool = False,
) -> str:
    """Return the safe publish action for this repository context."""

    del backup_requested
    if not destination_exists:
        return "create"
    return "backup_then_replace"
