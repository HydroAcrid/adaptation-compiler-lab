"""Render an incident-bundle handoff for a macOS responder."""

from __future__ import annotations


def build_incident_handoff(
    purpose: str,
    log_path: str,
    bundle_path: str,
) -> str:
    """Return the incident handoff as deterministic plain text."""

    return "\n".join(
        (
            "Commands:",
            f"Test-Path {log_path}",
            f"Copy-Item {log_path} {bundle_path}",
            f"Reason: {purpose}",
        )
    )
