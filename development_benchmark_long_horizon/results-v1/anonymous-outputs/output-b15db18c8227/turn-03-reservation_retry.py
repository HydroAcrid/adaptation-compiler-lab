_RESERVED: set[str] = set()


def reserve_for_job(job_id: str, names: list[str]) -> tuple[str, ...]:
    normalized = tuple(name.strip().casefold() for name in names)
    fresh = tuple(name for name in normalized if name not in _RESERVED)
    _RESERVED.update(fresh)
    return fresh
