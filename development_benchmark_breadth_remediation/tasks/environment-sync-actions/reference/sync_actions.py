"""Plan synchronization using stable public action tokens."""

from pathlib import Path

CREATE = "create"
NO_CHANGE = "no_change"
REPORT_RISK = "report_risk"
REFUSE = "refuse"
CREATE_BACKUP = "create_backup"
SYNC = "sync"
VERIFY = "verify"
RESTORE_HINT = "restore_hint"


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
        return (CREATE,)
    if not contents_differ:
        return (NO_CHANGE,)
    if not replace_authorized:
        return (REPORT_RISK, REFUSE)
    return (REPORT_RISK, CREATE_BACKUP, SYNC, VERIFY, RESTORE_HINT)
