"""Render a support plan without executing any of its command strings."""

from __future__ import annotations


def render_support_plan(purpose: str, commands: list[str]) -> str:
    """Return a deterministic human-readable plan."""

    if not purpose.strip():
        raise ValueError("purpose is required")
    if not commands or any(not command.strip() for command in commands):
        raise ValueError("at least one non-empty command is required")
    lines = [f"$ {command}" for command in commands]
    lines.append(f"Purpose: {purpose.strip()}")
    return "\n".join(lines)
