"""Plan local synchronization."""


class UnsafeLayoutError(ValueError):
    pass


def plan_sync(
    source: str,
    destination: str,
    destination_exists: bool,
    contents_differ: bool,
    replace_authorized: bool = False,
) -> tuple[str, ...]:
    if not destination_exists:
        return ("copy",)
    if not contents_differ:
        return ("no_change",)
    return ("sync",)
