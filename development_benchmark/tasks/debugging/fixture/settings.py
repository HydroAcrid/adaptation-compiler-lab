"""Resolve an application timeout from a supplied environment mapping."""

from __future__ import annotations

from collections.abc import Mapping

_CACHE: dict[str, int] = {}


def effective_timeout(environment: Mapping[str, str]) -> int:
    """Return APP_TIMEOUT or the safe default of 30 seconds."""

    cache_key = "APP_TIMEOUT"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    raw = environment.get("APP_TIMEOUT", "30").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 30
    if value <= 0:
        value = 30
    _CACHE[cache_key] = value
    return value
