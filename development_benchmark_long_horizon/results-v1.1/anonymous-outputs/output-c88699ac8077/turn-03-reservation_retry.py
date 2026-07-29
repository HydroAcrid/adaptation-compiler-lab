_RESERVED: dict[str, set[str]] = {}


def reserve_for_job(job_id: str, names: list[str]) -> tuple[str, ...]:
    normalized = tuple(name.strip().casefold() for name in names)
    reserved = _RESERVED.setdefault(job_id, set())
    fresh = tuple(name for name in normalized if name not in reserved)
    reserved.update(fresh)
    return fresh
