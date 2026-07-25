"""Resolve feature flags for one request."""

from __future__ import annotations

from collections.abc import Mapping

_effective_flags: dict[str, bool] = {}


def resolve_flags(
    defaults: Mapping[str, bool],
    tenant_overrides: Mapping[str, bool],
) -> dict[str, bool]:
    """Return the effective flags for one tenant request."""

    _effective_flags.update({key.strip().casefold(): value for key, value in defaults.items()})
    _effective_flags.update(
        {key.strip().casefold(): value for key, value in tenant_overrides.items()}
    )
    return dict(_effective_flags)
