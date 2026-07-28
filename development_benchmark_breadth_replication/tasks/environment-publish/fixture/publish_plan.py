"""Plan an asset publish."""


def plan_publish(
    destination_exists: bool,
    contents_differ: bool,
    replace_authorized: bool = False,
) -> tuple[str, ...]:
    if not destination_exists:
        return ("create",)
    if not contents_differ:
        return ("no_change",)
    return ("replace",)
