"""Governed external releases and compact target-visible runtime projections."""

from adaptation_compiler_lab.runtime.compiler import (
    RuntimeProjectionError,
    build_external_governed_releases,
    build_runtime_projection,
)
from adaptation_compiler_lab.runtime.decisions import bind_decision_release
from adaptation_compiler_lab.runtime.models import (
    ArtifactDecisionTable,
    ArtifactGovernanceBinding,
    BehavioralDecisionCase,
    CanonicalRuntimeProjection,
    ClauseProvenanceBinding,
    ExternalDecisionRelease,
    ExternalGovernedRelease,
    GovernedLifecycleEvent,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
)

__all__ = [
    "ArtifactDecisionTable",
    "ArtifactGovernanceBinding",
    "BehavioralDecisionCase",
    "CanonicalRuntimeProjection",
    "ClauseProvenanceBinding",
    "ExternalDecisionRelease",
    "ExternalGovernedRelease",
    "GovernedLifecycleEvent",
    "RuntimeClause",
    "RuntimeClauseRole",
    "RuntimeProjectionContext",
    "RuntimeProjectionError",
    "RuntimeProjectionManifest",
    "bind_decision_release",
    "build_external_governed_releases",
    "build_runtime_projection",
]
