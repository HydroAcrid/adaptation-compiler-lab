"""Compact complete-branch Codex projection for typed decisions."""

from __future__ import annotations

from typing import Final, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import ArtifactRef, FrozenModel, Sha256Digest
from adaptation_compiler_lab.runtime.compiler import build_runtime_projection
from adaptation_compiler_lab.runtime.models import (
    ArtifactDecisionTable,
    BehavioralDecisionCase,
    CanonicalRuntimeProjection,
    ClauseProvenanceBinding,
    ExternalDecisionRelease,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.codex_runtime import ExactRenderedText
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind

CODEX_RUNTIME_V4_RENDERER_ID: Final = "codex-decision-table-runtime"
CODEX_RUNTIME_V4_RENDERER_VERSION: Final = "2.1.0"
_VERIFICATION_COMPACTION = {
    "Verify the selected publish action before completion.": "Verify action.",
}


class RenderedDecisionTableProjection(FrozenModel):
    """Target-visible complete branch table with external lineage."""

    renderer_id: Literal["codex-decision-table-runtime"] = CODEX_RUNTIME_V4_RENDERER_ID
    renderer_version: Literal["2.1.0"] = CODEX_RUNTIME_V4_RENDERER_VERSION
    target_family: Literal["codex"] = "codex"
    content: ExactRenderedText
    content_digest: Sha256Digest
    utf8_bytes: int = Field(ge=1)
    clause_digests: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def content_measurement_is_exact(self) -> Self:
        if self.content_digest != sha256_text(self.content):
            raise ValueError("decision-table content digest is inconsistent")
        if self.utf8_bytes != len(self.content.encode("utf-8")):
            raise ValueError("decision-table UTF-8 byte count is inconsistent")
        return self


def _scope_prefix(project_ids: tuple[str, ...]) -> str:
    if not project_ids:
        return ""
    return f"[{','.join(project_ids)}] "


def _decision_text(
    decision: BehavioralDecisionCase,
    *,
    project_ids: tuple[str, ...],
) -> str:
    actions = " -> ".join(decision.required_actions)
    text = f"{_scope_prefix(project_ids)}{decision.situation}: {actions}"
    if decision.forbidden_actions:
        text += f"; never {', '.join(decision.forbidden_actions)}"
    return f"{text}."


def build_codex_runtime_projection_v4(
    release: ExternalDecisionRelease,
    context: RuntimeProjectionContext,
) -> CanonicalRuntimeProjection:
    """Project every explicit branch and its unlisted-case preservation rule."""

    governed = release.governed_release
    baseline = build_runtime_projection(governed, context)
    applicable_ids = {
        source.record_id
        for clause in baseline.clauses
        if RuntimeClauseRole.ACTIONABLE_BEHAVIOR in clause.roles
        for source in clause.source_artifact_refs
    }
    tables_by_id: dict[str, ArtifactDecisionTable] = {
        item.artifact_ref.record_id: item for item in release.decision_tables
    }
    active = tuple(
        sorted(
            (
                (artifact, tables_by_id[artifact.artifact_ref.record_id])
                for artifact in governed.active_artifacts
                if artifact.artifact_ref.record_id in applicable_ids
            ),
            key=lambda item: (-item[0].precedence, item[0].artifact_ref.record_id),
        )
    )
    if not active:
        raise ValueError("Codex decision-table projection has no applicable behavior")

    clauses: list[RuntimeClause] = []
    for artifact, table in active:
        project_ids = artifact.scope.project_ids
        roles = (
            (
                RuntimeClauseRole.ACTIONABLE_BEHAVIOR,
                RuntimeClauseRole.NECESSARY_SCOPE,
            )
            if project_ids
            else (RuntimeClauseRole.ACTIONABLE_BEHAVIOR,)
        )
        clauses.extend(
            RuntimeClause(
                text=_decision_text(decision, project_ids=project_ids),
                roles=roles,
                source_artifact_refs=(artifact.artifact_ref,),
            )
            for decision in table.cases
        )

    verification_sources: dict[str, list[ArtifactRef]] = {}
    for artifact, _table in active:
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
                text=_VERIFICATION_COMPACTION.get(requirement, requirement),
                roles=(RuntimeClauseRole.NECESSARY_VERIFICATION,),
                source_artifact_refs=sources,
            )
        )
    return CanonicalRuntimeProjection(
        external_release_digest=release.content_digest,
        release_ref=governed.release_ref,
        context=context,
        clauses=tuple(clauses),
        omitted_artifact_refs=baseline.omitted_artifact_refs,
    )


def render_codex_runtime_projection_v4(
    projection: CanonicalRuntimeProjection,
) -> RenderedDecisionTableProjection:
    """Render the canonical branch table without governance metadata."""

    if (
        ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        or projection.context.target_family != TargetKind.CODEX.value
    ):
        raise ValueError("Codex decision-table renderer requires a known Codex target")
    if not projection.clauses:
        raise ValueError("Codex decision-table projection cannot be empty")
    content = "".join(f"- {clause.text}\n" for clause in projection.clauses)
    return RenderedDecisionTableProjection(
        content=content,
        content_digest=sha256_text(content),
        utf8_bytes=len(content.encode("utf-8")),
        clause_digests=tuple(clause.content_digest for clause in projection.clauses),
    )


def build_runtime_projection_manifest_v4(
    *,
    release: ExternalDecisionRelease,
    projection: CanonicalRuntimeProjection,
    rendered: RenderedDecisionTableProjection,
) -> RuntimeProjectionManifest:
    """Bind every compact branch to exact governed evidence lineage."""

    if projection.external_release_digest != release.content_digest:
        raise ValueError("runtime v4 projection does not bind the supplied release")
    if projection != build_codex_runtime_projection_v4(release, projection.context):
        raise ValueError("runtime v4 projection is not canonical")
    if rendered != render_codex_runtime_projection_v4(projection):
        raise ValueError("runtime v4 rendered content drifted")
    bindings_by_artifact = {
        item.artifact_ref.record_id: item for item in release.governed_release.active_bindings
    }
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
