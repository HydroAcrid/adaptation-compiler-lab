"""Intentionally defective shell rendering used by benchmark conformance tests."""

from __future__ import annotations


def build_incident_handoff(
    purpose: str,
    log_path: str,
    bundle_path: str,
) -> str:
    """Return paths in unsafe double-quoted shell strings."""

    return "\n".join(
        (
            f"Reason: {purpose}",
            "",
            "Commands for macOS zsh:",
            f'test -f "{log_path}"',
            f'cp "{log_path}" "{bundle_path}"',
        )
    )
