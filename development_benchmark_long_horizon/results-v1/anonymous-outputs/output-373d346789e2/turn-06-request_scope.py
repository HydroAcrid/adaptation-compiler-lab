_CURRENT: dict[str, str] = {}


def begin_request(request_id: str, values: dict[str, str]) -> dict[str, str]:
    _CURRENT.update(values)
    _CURRENT["request_id"] = request_id
    return dict(_CURRENT)
