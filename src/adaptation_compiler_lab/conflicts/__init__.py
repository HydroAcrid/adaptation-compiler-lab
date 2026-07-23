"""Deterministic conflict precedence for scoped adaptation artifacts."""

from adaptation_compiler_lab.conflicts.policy import (
    ConflictDecision,
    resolve_artifact_conflict,
)

__all__ = ["ConflictDecision", "resolve_artifact_conflict"]
