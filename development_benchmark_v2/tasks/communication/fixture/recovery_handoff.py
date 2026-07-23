"""Render a deterministic recovery handoff for the Windows support team."""

from __future__ import annotations


def build_recovery_handoff(
    purpose: str,
    archive_path: str,
    destination_path: str,
) -> str:
    """Return the recovery handoff as plain text."""

    return "\n".join(
        (
            "Recovery commands:",
            f"cp -a {archive_path} {destination_path}",
            f"test -e {destination_path} && echo restored",
            "",
            f"Purpose: {purpose}",
        )
    )
