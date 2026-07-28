"""Resolve request-local options."""

_DEFAULT_OPTIONS = {"timeout": 30, "retries": 2}


def resolve_options(request_options: dict[str, int]) -> dict[str, int]:
    normalized = {key.strip(): value for key, value in request_options.items()}
    return {**_DEFAULT_OPTIONS, **normalized}
