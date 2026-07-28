"""Plan a recoverable local migration without executing it."""

CREATE = "create"
NO_CHANGE = "no_change"
REPORT_RISK = "report_risk"
REFUSE = "refuse"
CREATE_BACKUP = "create_backup"
VERIFY_BACKUP = "verify_backup"
REPLACE = "replace"
RESTORE_HINT = "restore_hint"


def plan_migration(
    destination_exists: bool,
    contents_differ: bool,
    replace_authorized: bool = False,
) -> tuple[str, ...]:
    if not destination_exists:
        return (CREATE,)
    if not contents_differ:
        return (NO_CHANGE,)
    if not replace_authorized:
        return (REPORT_RISK, REFUSE)
    return (
        REPORT_RISK,
        CREATE_BACKUP,
        VERIFY_BACKUP,
        REPLACE,
        RESTORE_HINT,
    )
