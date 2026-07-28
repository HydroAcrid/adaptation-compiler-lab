"""Resolve request-local options."""

_DEFAULT_OPTIONS = {"timeout": 30, "retries": 2}
_ACTIVE_OPTIONS = dict(_DEFAULT_OPTIONS)


def resolve_options(request_options: dict[str, int]) -> dict[str, int]:
    normalized = {key.strip(): value for key, value in request_options.items()}
    _ACTIVE_OPTIONS.update(normalized)
    return dict(_ACTIVE_OPTIONS)
