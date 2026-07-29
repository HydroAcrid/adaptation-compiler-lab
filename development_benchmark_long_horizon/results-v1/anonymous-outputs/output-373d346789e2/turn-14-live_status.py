_LAST_HEALTH = "healthy"


def deployment_health(checks: list[bool]) -> str:
    global _LAST_HEALTH
    if checks:
        _LAST_HEALTH = "healthy" if all(checks) else "degraded"
    return _LAST_HEALTH
