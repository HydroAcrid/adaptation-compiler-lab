"""Target-natural Codex rendering for portable semantic decisions."""

from __future__ import annotations

from collections import defaultdict
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import ArtifactRef, FrozenModel, Sha256Digest
from adaptation_compiler_lab.runtime.compiler import build_runtime_projection
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    ClauseProvenanceBinding,
    DecisionOperation,
    DecisionResourceClass,
    ExternalSemanticDecisionRelease,
    RecoveryRequestState,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
    SemanticDecisionCase,
)
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.codex_runtime import ExactRenderedText
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind

CODEX_RUNTIME_V5_RENDERER_ID: Final = "codex-semantic-decision-runtime"
CODEX_RUNTIME_V5_RENDERER_VERSION: Final = "3.0.0"
_HEADER: Final = "Apply user rules over defaults.\n"
_BACKUP_REPLACE = (
    DecisionOperation.CREATE_RECOVERABLE_BACKUP,
    DecisionOperation.REPLACE_CONTENTS,
)
_ATOMIC_NO_BACKUP = (
    DecisionOperation.PREPARE_TEMPORARY_REPLACEMENT,
    DecisionOperation.ACTIVATE_ATOMICALLY,
)


class RenderedSemanticDecisionProjection(FrozenModel):
    """Target-visible natural rules with external semantic lineage."""

    renderer_id: Literal["codex-semantic-decision-runtime"] = CODEX_RUNTIME_V5_RENDERER_ID
    renderer_version: Literal["3.0.0"] = CODEX_RUNTIME_V5_RENDERER_VERSION
    target_family: Literal["codex"] = "codex"
    content: ExactRenderedText
    content_digest: Sha256Digest
    utf8_bytes: int = Field(ge=1)
    clause_digests: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def content_measurement_is_exact(self) -> Self:
        if self.content_digest != sha256_text(self.content):
            raise ValueError("semantic content digest is inconsistent")
        if self.utf8_bytes != len(self.content.encode("utf-8")):
            raise ValueError("semantic content byte count is inconsistent")
        return self


def _case_key(case: SemanticDecisionCase) -> tuple[object, ...]:
    return (
        case.resource_class,
        case.recovery_request,
        case.required_operations,
        case.forbidden_operations,
    )


def _semantic_clauses(
    release: ExternalSemanticDecisionRelease,
    applicable_ids: set[str],
) -> tuple[RuntimeClause, ...]:
    cases: dict[tuple[object, ...], list[ArtifactRef]] = defaultdict(list)
    scoped_keys: set[tuple[object, ...]] = set()
    for artifact, table in zip(
        release.governed_release.active_artifacts,
        release.decision_tables,
        strict=True,
    ):
        if artifact.artifact_ref.record_id not in applicable_ids:
            continue
        for case in table.cases:
            key = _case_key(case)
            if key in cases:
                raise ValueError("active semantic decisions overlap")
            cases[key].append(artifact.artifact_ref)
            if artifact.scope.project_ids:
                scoped_keys.add(key)

    def sources(key: tuple[object, ...]) -> tuple[ArtifactRef, ...]:
        return tuple(cases.pop(key))

    clauses: list[RuntimeClause] = []
    persistent_any = (
        DecisionResourceClass.PERSISTENT_USER_MANAGED,
        RecoveryRequestState.EITHER,
        _BACKUP_REPLACE,
        (),
    )
    if persistent_any in cases:
        clauses.append(
            RuntimeClause(
                text=(
                    "Create a recoverable backup before replacing existing persistent "
                    "user content, whether recovery was requested or not."
                ),
                roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                source_artifact_refs=sources(persistent_any),
            )
        )

    cache_any = (
        DecisionResourceClass.DISPOSABLE_GENERATED_CACHE,
        RecoveryRequestState.EITHER,
        _ATOMIC_NO_BACKUP,
        (DecisionOperation.CREATE_RECOVERABLE_BACKUP,),
    )
    if cache_any in cases:
        roles: tuple[RuntimeClauseRole, ...] = (RuntimeClauseRole.ACTIONABLE_BEHAVIOR,)
        if cache_any in scoped_keys:
            roles += (RuntimeClauseRole.NECESSARY_SCOPE,)
        clauses.append(
            RuntimeClause(
                text=(
                    "Replace existing disposable generated-cache content atomically without "
                    "a recovery copy, whether recovery was requested or not."
                ),
                roles=roles,
                source_artifact_refs=sources(cache_any),
            )
        )

    persistent_no = (
        DecisionResourceClass.PERSISTENT_USER_MANAGED,
        RecoveryRequestState.NOT_REQUESTED,
        (DecisionOperation.REFUSE_REPLACEMENT,),
        (DecisionOperation.REPLACE_CONTENTS,),
    )
    persistent_yes = (
        DecisionResourceClass.PERSISTENT_USER_MANAGED,
        RecoveryRequestState.REQUESTED,
        _BACKUP_REPLACE,
        (),
    )
    if persistent_no in cases or persistent_yes in cases:
        if persistent_no not in cases or persistent_yes not in cases:
            raise ValueError("semantic persistent exception is incomplete")
        clauses.append(
            RuntimeClause(
                text=(
                    "For existing persistent user content, replace only when recovery was "
                    "requested; create a recoverable backup first. Otherwise refuse."
                ),
                roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                source_artifact_refs=tuple(
                    sorted(
                        {
                            source.record_id: source
                            for source in (
                                *sources(persistent_no),
                                *sources(persistent_yes),
                            )
                        }.values(),
                        key=lambda ref: (
                            ref.record_id,
                            ref.record_version,
                            ref.content_digest,
                        ),
                    )
                ),
            )
        )

    preserve = (
        DecisionResourceClass.UNLISTED,
        RecoveryRequestState.NOT_APPLICABLE,
        (DecisionOperation.PRESERVE_BEHAVIOR,),
        (),
    )
    if preserve in cases:
        clauses.append(
            RuntimeClause(
                text="Preserve all unlisted behavior.",
                roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                source_artifact_refs=sources(preserve),
            )
        )
    if cases:
        raise ValueError("semantic renderer does not support an active decision combination")
    return tuple(clauses)


def build_codex_runtime_projection_v5(
    release: ExternalSemanticDecisionRelease,
    context: RuntimeProjectionContext,
) -> CanonicalRuntimeProjection:
    """Render semantic operations into concise target-natural rules."""

    governed = release.governed_release
    baseline = build_runtime_projection(governed, context)
    applicable_ids = {
        source.record_id
        for clause in baseline.clauses
        if RuntimeClauseRole.ACTIONABLE_BEHAVIOR in clause.roles
        for source in clause.source_artifact_refs
    }
    clauses = list(_semantic_clauses(release, applicable_ids))
    verification_sources: dict[str, list[ArtifactRef]] = defaultdict(list)
    for artifact in governed.active_artifacts:
        if artifact.artifact_ref.record_id not in applicable_ids:
            continue
        for requirement in artifact.behavioral_contract.verification_requirements:
            verification_sources[requirement].append(artifact.artifact_ref)
    if verification_sources:
        clauses.append(
            RuntimeClause(
                text="Verify the selected action.",
                roles=(RuntimeClauseRole.NECESSARY_VERIFICATION,),
                source_artifact_refs=tuple(
                    sorted(
                        {source for values in verification_sources.values() for source in values},
                        key=lambda ref: (
                            ref.record_id,
                            ref.record_version,
                            ref.content_digest,
                        ),
                    )
                ),
            )
        )
    if not clauses:
        raise ValueError("Codex semantic projection has no applicable behavior")
    return CanonicalRuntimeProjection(
        external_release_digest=release.content_digest,
        release_ref=governed.release_ref,
        context=context,
        clauses=tuple(clauses),
        omitted_artifact_refs=baseline.omitted_artifact_refs,
    )


def render_codex_runtime_projection_v5(
    projection: CanonicalRuntimeProjection,
) -> RenderedSemanticDecisionProjection:
    """Render natural rules while keeping the directive renderer-owned."""

    if (
        ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        or projection.context.target_family != TargetKind.CODEX.value
    ):
        raise ValueError("Codex semantic renderer requires a known Codex target")
    content = _HEADER + "".join(f"- {clause.text}\n" for clause in projection.clauses)
    return RenderedSemanticDecisionProjection(
        content=content,
        content_digest=sha256_text(content),
        utf8_bytes=len(content.encode("utf-8")),
        clause_digests=tuple(clause.content_digest for clause in projection.clauses),
    )


def build_runtime_projection_manifest_v5(
    *,
    release: ExternalSemanticDecisionRelease,
    projection: CanonicalRuntimeProjection,
    rendered: RenderedSemanticDecisionProjection,
) -> RuntimeProjectionManifest:
    """Bind each natural rule to exact governed evidence lineage."""

    if projection.external_release_digest != release.content_digest:
        raise ValueError("runtime v5 projection does not bind the supplied release")
    if projection != build_codex_runtime_projection_v5(release, projection.context):
        raise ValueError("runtime v5 projection is not canonical")
    if rendered != render_codex_runtime_projection_v5(projection):
        raise ValueError("runtime v5 rendered content drifted")
    bindings_by_artifact = {
        item.artifact_ref.record_id: item for item in release.governed_release.active_bindings
    }
    return RuntimeProjectionManifest(
        external_release_digest=release.content_digest,
        runtime_projection_digest=projection.content_digest,
        target_renderer_id=rendered.renderer_id,
        target_renderer_version=rendered.renderer_version,
        rendered_content_digest=rendered.content_digest,
        rendered_utf8_bytes=rendered.utf8_bytes,
        clause_bindings=tuple(
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
        ),
    )
