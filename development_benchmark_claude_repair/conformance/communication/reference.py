"""Render an incident-bundle handoff for a macOS responder."""

from __future__ import annotations

import shlex


def build_incident_handoff(
    purpose: str,
    log_path: str,
    bundle_path: str,
) -> str:
    """Return the incident handoff as deterministic plain text."""

    quoted_log = shlex.quote(log_path)
    quoted_bundle = shlex.quote(bundle_path)
    return "\n".join(
        (
            f"Reason: {purpose}",
            "",
            "Commands for macOS zsh:",
            f"test -f {quoted_log}",
            f"cp {quoted_log} {quoted_bundle}",
        )
    )
