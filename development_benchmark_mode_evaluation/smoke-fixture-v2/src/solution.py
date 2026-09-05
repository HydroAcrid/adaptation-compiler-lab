"""Deliberately incomplete policy used only by the v2 instrument smoke."""


def clamp_attempts(requested: int, ceiling: int) -> int:
    """Return an allowed retry count."""

    if requested < 0 or ceiling < 1:
        raise ValueError("invalid retry bounds")
    return ceiling
