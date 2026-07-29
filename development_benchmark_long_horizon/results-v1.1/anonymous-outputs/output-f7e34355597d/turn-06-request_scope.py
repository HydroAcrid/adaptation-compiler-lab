def begin_request(request_id: str, values: dict[str, str]) -> dict[str, str]:
    scope = dict(values)
    scope["request_id"] = request_id
    return scope
