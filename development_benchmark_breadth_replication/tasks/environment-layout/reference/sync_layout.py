"""Plan local synchronization."""

from pathlib import Path


class UnsafeLayoutError(ValueError):
    pass


def plan_sync(
    source: str,
    destination: str,
    destination_exists: bool,
    contents_differ: bool,
    replace_authorized: bool = False,
) -> tuple[str, ...]:
    source_path = Path(source).resolve(strict=False)
    destination_path = Path(destination).resolve(strict=False)
    if (
        source_path == destination_path
        or source_path in destination_path.parents
        or destination_path in source_path.parents
    ):
        raise UnsafeLayoutError("source and destination overlap")
    if not destination_exists:
        return ("copy",)
    if not contents_differ:
        return ("no_change",)
    if not replace_authorized:
        return ("report_risk", "refuse")
    return ("report_risk", "create_backup", "sync", "verify", "restore_hint")
