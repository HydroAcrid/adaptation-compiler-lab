"""Changing these defaults requires a successor evaluation version."""

SUPPORT_TASKS = 3
SUPPORT_DATES = 2
TRIAL_DAYS = 14
CHECKED_OPPORTUNITIES = 3
COMPLIANCE_SUCCESSES = 2
RAW_RETENTION_DAYS = 30
MAX_PROFILE_BYTES = 1_500
MAX_DAILY_ANALYSES = 12
POLL_MINUTES = 5
MIN_REMAINING_CAPACITY = 20


def frozen_defaults() -> dict[str, int]:
    return {
        name: value
        for name, value in globals().items()
        if name.isupper() and isinstance(value, int)
    }
