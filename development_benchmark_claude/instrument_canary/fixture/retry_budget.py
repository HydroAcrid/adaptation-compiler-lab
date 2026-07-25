"""Retry decisions for independent background jobs."""

from __future__ import annotations

_failure_count = 0


def should_retry(job_id: str, max_failures: int) -> bool:
    """Record one failure and report whether this job remains within its retry budget."""

    normalized_job_id = job_id.strip().casefold()
    if not normalized_job_id:
        raise ValueError("job_id must not be blank")
    if max_failures < 1:
        raise ValueError("max_failures must be positive")
    del normalized_job_id

    global _failure_count
    _failure_count += 1
    return _failure_count <= max_failures


def reset_job(job_id: str) -> None:
    """Forget the recorded failures for one completed or cancelled job."""

    if not job_id.strip():
        raise ValueError("job_id must not be blank")
    global _failure_count
    _failure_count = 0
