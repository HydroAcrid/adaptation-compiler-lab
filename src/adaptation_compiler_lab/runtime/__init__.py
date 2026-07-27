"""Governed external releases and compact target-visible runtime projections."""

from adaptation_compiler_lab.runtime.compiler import (
    RuntimeProjectionError,
    build_external_governed_releases,
    build_runtime_projection,
)
from adaptation_compiler_lab.runtime.models import (
    ArtifactGovernanceBinding,
    CanonicalRuntimeProjection,
    ClauseProvenanceBinding,
    ExternalGovernedRelease,
    GovernedLifecycleEvent,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
)

__all__ = [
    "ArtifactGovernanceBinding",
    "CanonicalRuntimeProjection",
    "ClauseProvenanceBinding",
    "ExternalGovernedRelease",
    "GovernedLifecycleEvent",
    "RuntimeClause",
    "RuntimeClauseRole",
    "RuntimeProjectionContext",
    "RuntimeProjectionError",
    "RuntimeProjectionManifest",
    "build_external_governed_releases",
    "build_runtime_projection",
]
