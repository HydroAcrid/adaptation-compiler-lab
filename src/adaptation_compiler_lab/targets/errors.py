"""Structured target-rendering failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderViolation:
    """One fail-closed renderer policy violation."""

    code: str
    message: str
    artifact_id: str | None = None


class TargetRenderError(ValueError):
    """Raised when a target cannot faithfully and safely represent a release."""

    def __init__(self, violations: tuple[RenderViolation, ...]) -> None:
        if not violations:
            raise ValueError("TargetRenderError requires at least one violation")
        self.violations = violations
        summary = "; ".join(
            f"{item.code}{f'[{item.artifact_id}]' if item.artifact_id else ''}: {item.message}"
            for item in violations
        )
        super().__init__(summary)
