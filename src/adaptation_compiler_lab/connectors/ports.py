"""Narrow hexagonal ports for Milestone 4 and later sealed workflows."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from adaptation_compiler_lab.connectors.models import (
    ScoringRequest,
    ScoringResult,
    SourceTaskPage,
    SourceTaskSnapshot,
    TargetRunRequest,
    TargetRunResult,
)
from adaptation_compiler_lab.domain.base import Sha256Digest


@runtime_checkable
class SourceConnector(Protocol):
    """List privacy-minimized source tasks and read one exact completed task."""

    @property
    def source_version(self) -> str:
        """Return the pinned source executable version."""

    @property
    def source_schema_digest(self) -> Sha256Digest:
        """Return the pinned generated protocol-bundle digest."""

    def list_completed_tasks(
        self,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> SourceTaskPage:
        """List terminal-task candidates without returning raw thread content."""

    def read_completed_task(self, task_id: str) -> SourceTaskSnapshot:
        """Read one full persisted task after the caller has authorized that exact ID."""


@runtime_checkable
class TargetRunner(Protocol):
    """Execute exactly one target run inside a fresh, fail-closed environment."""

    def run(self, request: TargetRunRequest) -> TargetRunResult:
        """Run the blinded request and return a structured trace."""


@runtime_checkable
class Scorer(Protocol):
    """Score condition-blind evidence independently of the target agent."""

    def score(self, request: ScoringRequest) -> ScoringResult:
        """Return rubric components without receiving a condition label."""
