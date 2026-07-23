"""Resolve the timeout for one request."""

from __future__ import annotations

from collections.abc import Mapping

DEFAULT_TIMEOUT_SECONDS = 30
_last_timeout_seconds = DEFAULT_TIMEOUT_SECONDS


def timeout_for_request(headers: Mapping[str, str]) -> int:
    """Return the request timeout after normalizing HTTP-style headers."""

    normalized = {name.strip().casefold(): value.strip() for name, value in headers.items()}
    override = normalized.get("x-request-timeout")

    global _last_timeout_seconds
    if override is not None:
        _last_timeout_seconds = int(override)
    return _last_timeout_seconds
