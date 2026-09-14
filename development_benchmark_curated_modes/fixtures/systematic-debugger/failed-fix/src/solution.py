"""Construct delivery policies for two independent jobs."""


def build_policy_pair(
    first_job,
    first_headers,
    first_retry,
    second_job,
    second_headers,
    second_retry,
):
    """Build two policies without changing the shared template."""

    if not first_job or not second_job:
        raise ValueError("job_id is required")
    template = {"headers": {"Accept": "application/json"}, "retry_delays": []}
    first = template.copy()
    first["headers"].update(first_headers)
    if first_retry is not None:
        if first_retry < 0:
            raise ValueError("retry_delay cannot be negative")
        first["retry_delays"].append(first_retry)
    first_result = {
        "headers": dict(first["headers"]),
        "job_id": first_job,
        "retry_delays": tuple(first["retry_delays"]),
    }
    second = template.copy()
    second["headers"].update(second_headers)
    if second_retry is not None:
        if second_retry < 0:
            raise ValueError("retry_delay cannot be negative")
        second["retry_delays"].append(second_retry)
    second_result = {
        "headers": dict(second["headers"]),
        "job_id": second_job,
        "retry_delays": tuple(second["retry_delays"]),
    }
    return first_result, second_result
