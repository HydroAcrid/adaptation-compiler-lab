"""Construction of typed decision releases without mutating v1 artifacts."""

from __future__ import annotations

from adaptation_compiler_lab.runtime.models import (
    ArtifactDecisionTable,
    ExternalDecisionRelease,
    ExternalGovernedRelease,
    ExternalSemanticDecisionRelease,
    SemanticDecisionTable,
)


def bind_decision_release(
    release: ExternalGovernedRelease,
    available_tables: tuple[ArtifactDecisionTable, ...],
) -> ExternalDecisionRelease:
    """Select exact tables for the active release or fail closed."""

    by_id = {item.artifact_ref.record_id: item for item in available_tables}
    if len(by_id) != len(available_tables):
        raise ValueError("available decision tables contain duplicate artifact IDs")
    selected: list[ArtifactDecisionTable] = []
    for artifact in release.active_artifacts:
        table = by_id.get(artifact.artifact_ref.record_id)
        if table is None or table.artifact_ref != artifact.artifact_ref:
            raise ValueError("an active artifact lacks its exact decision table")
        selected.append(table)
    return ExternalDecisionRelease(
        governed_release=release,
        decision_tables=tuple(selected),
    )


def bind_semantic_decision_release(
    release: ExternalGovernedRelease,
    available_tables: tuple[SemanticDecisionTable, ...],
) -> ExternalSemanticDecisionRelease:
    """Select exact semantic tables for the active release or fail closed."""

    by_id = {item.artifact_ref.record_id: item for item in available_tables}
    if len(by_id) != len(available_tables):
        raise ValueError("available semantic tables contain duplicate artifact IDs")
    selected: list[SemanticDecisionTable] = []
    for artifact in release.active_artifacts:
        table = by_id.get(artifact.artifact_ref.record_id)
        if table is None or table.artifact_ref != artifact.artifact_ref:
            raise ValueError("an active artifact lacks its exact semantic decision table")
        selected.append(table)
    return ExternalSemanticDecisionRelease(
        governed_release=release,
        decision_tables=tuple(selected),
    )
