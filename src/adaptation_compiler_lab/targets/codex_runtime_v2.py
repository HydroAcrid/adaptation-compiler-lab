"""Semantics-preserving compact Codex projection with external lineage."""

from __future__ import annotations

from typing import Final

from adaptation_compiler_lab.domain import ArtifactRef
from adaptation_compiler_lab.runtime.compiler import build_runtime_projection
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    ClauseProvenanceBinding,
    ExternalGovernedRelease,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.codex_runtime import RenderedRuntimeProjection
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind

CODEX_RUNTIME_V2_RENDERER_ID: Final = "codex-compact-runtime"
CODEX_RUNTIME_V2_RENDERER_VERSION: Final = "1.1.0"


def _scoped_behavior(*, behavior: str, project_ids: tuple[str, ...]) -> str:
    if not project_ids:
        return behavior
    scope = ", ".join(project_ids)
    if behavior.startswith("For ") and ", " in behavior:
        subject, action = behavior.removeprefix("For ").split(", ", maxsplit=1)
        return f"Project {scope} — {subject}: {action}"
    return f"Project {scope}: {behavior}"


def build_codex_runtime_projection_v2(
    release: ExternalGovernedRelease,
    context: RuntimeProjectionContext,
) -> CanonicalRuntimeProjection:
    """Project active behavior once, retaining scope and deduplicating verification."""

    baseline = build_runtime_projection(release, context)
    applicable_ids = {
        source.record_id
        for clause in baseline.clauses
        if RuntimeClauseRole.ACTIONABLE_BEHAVIOR in clause.roles
        for source in clause.source_artifact_refs
    }
    active = tuple(
        sorted(
            (
                artifact
                for artifact in release.active_artifacts
                if artifact.artifact_ref.record_id in applicable_ids
            ),
            key=lambda artifact: (-artifact.precedence, artifact.artifact_ref.record_id),
        )
    )
    if not active:
        raise ValueError("compact Codex v2 projection has no applicable active behavior")

    clauses: list[RuntimeClause] = []
    for artifact in active:
        project_ids = artifact.scope.project_ids
        roles = (
            (
                RuntimeClauseRole.ACTIONABLE_BEHAVIOR,
                RuntimeClauseRole.NECESSARY_SCOPE,
            )
            if project_ids
            else (RuntimeClauseRole.ACTIONABLE_BEHAVIOR,)
        )
        for behavior in artifact.behavioral_contract.required_behaviors:
            clauses.append(
                RuntimeClause(
                    text=_scoped_behavior(
                        behavior=behavior,
                        project_ids=project_ids,
                    ),
                    roles=roles,
                    source_artifact_refs=(artifact.artifact_ref,),
                )
            )

    verification_sources: dict[str, list[ArtifactRef]] = {}
    for artifact in active:
        for requirement in artifact.behavioral_contract.verification_requirements:
            verification_sources.setdefault(requirement, []).append(artifact.artifact_ref)
    for requirement in sorted(verification_sources):
        sources = tuple(
            sorted(
                verification_sources[requirement],
                key=lambda ref: (ref.record_id, ref.record_version, ref.content_digest),
            )
        )
        clauses.append(
            RuntimeClause(
                text=requirement,
                roles=(RuntimeClauseRole.NECESSARY_VERIFICATION,),
                source_artifact_refs=sources,
            )
        )
    return CanonicalRuntimeProjection(
        external_release_digest=release.content_digest,
        release_ref=release.release_ref,
        context=context,
        clauses=tuple(clauses),
        omitted_artifact_refs=baseline.omitted_artifact_refs,
    )


def render_codex_runtime_projection_v2(
    projection: CanonicalRuntimeProjection,
) -> RenderedRuntimeProjection:
    """Render the already-minimized typed clauses without internal metadata."""

    if (
        ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        or projection.context.target_family != TargetKind.CODEX.value
    ):
        raise ValueError("Codex runtime v2 renderer requires a known Codex target family")
    if not projection.clauses:
        raise ValueError("Codex runtime v2 projection cannot be empty")
    content = "".join(f"- {clause.text}\n" for clause in projection.clauses)
    return RenderedRuntimeProjection(
        renderer_version=CODEX_RUNTIME_V2_RENDERER_VERSION,
        content=content,
        content_digest=sha256_text(content),
        utf8_bytes=len(content.encode("utf-8")),
        clause_digests=tuple(clause.content_digest for clause in projection.clauses),
    )


def build_runtime_projection_manifest_v2(
    *,
    release: ExternalGovernedRelease,
    projection: CanonicalRuntimeProjection,
    rendered: RenderedRuntimeProjection,
) -> RuntimeProjectionManifest:
    """Bind every minimized clause back to exact governed evidence lineage."""

    if projection.external_release_digest != release.content_digest:
        raise ValueError("runtime v2 projection does not bind the supplied release")
    expected_projection = build_codex_runtime_projection_v2(release, projection.context)
    if projection != expected_projection:
        raise ValueError("runtime v2 projection is not canonical")
    expected_rendered = render_codex_runtime_projection_v2(projection)
    if rendered != expected_rendered:
        raise ValueError("runtime v2 rendered content drifted")
    bindings_by_artifact = {item.artifact_ref.record_id: item for item in release.active_bindings}
    clause_bindings = tuple(
        ClauseProvenanceBinding(
            clause_digest=clause.content_digest,
            rendered_fragment_digest=sha256_text(f"- {clause.text}\n"),
            source_binding_digests=tuple(
                sorted(
                    {
                        bindings_by_artifact[source.record_id].content_digest
                        for source in clause.source_artifact_refs
                    }
                )
            ),
        )
        for clause in projection.clauses
    )
    return RuntimeProjectionManifest(
        external_release_digest=release.content_digest,
        runtime_projection_digest=projection.content_digest,
        target_renderer_id=rendered.renderer_id,
        target_renderer_version=rendered.renderer_version,
        rendered_content_digest=rendered.content_digest,
        rendered_utf8_bytes=rendered.utf8_bytes,
        clause_bindings=clause_bindings,
    )
