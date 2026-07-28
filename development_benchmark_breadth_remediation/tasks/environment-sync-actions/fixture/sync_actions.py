"""Plan synchronization using stable public action tokens."""

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
    if not destination_exists:
        return (CREATE,)
    if not contents_differ:
        return (NO_CHANGE,)
    return (SYNC,)
