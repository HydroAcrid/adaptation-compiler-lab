def begin_request(request_id: str, values: dict[str, str]) -> dict[str, str]:
    current = dict(values)
    current["request_id"] = request_id
    return current
