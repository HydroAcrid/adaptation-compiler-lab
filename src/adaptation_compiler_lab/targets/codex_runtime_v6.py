"""Closed-world Codex rendering for portable semantic decisions."""

from __future__ import annotations

from typing import Final, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    ClauseProvenanceBinding,
    ExternalSemanticDecisionRelease,
    RuntimeClause,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.codex_runtime import ExactRenderedText
from adaptation_compiler_lab.targets.codex_runtime_v5 import (
    build_codex_runtime_projection_v5,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind

CODEX_RUNTIME_V6_RENDERER_ID: Final = "codex-semantic-decision-runtime"
CODEX_RUNTIME_V6_RENDERER_VERSION: Final = "3.1.0"
_HEADER: Final = "Apply only these rules; infer no others from operation names.\n"
_TEXT_REWRITES: Final = {
    (
        "Create a recoverable backup before replacing existing persistent user content, "
        "whether recovery was requested or not."
    ): (
        "Existing persistent user content: always back up before replacement, even without "
        "a recovery request."
    ),
    (
        "Replace existing disposable generated-cache content atomically without a recovery "
        "copy, whether recovery was requested or not."
    ): (
        "Existing disposable generated-cache content: replace atomically without a recovery "
        "copy, even when one was requested."
    ),
    (
        "For existing persistent user content, replace only when recovery was requested; "
        "create a recoverable backup first. Otherwise refuse."
    ): (
        "Existing persistent user content: replace only when recovery was requested; back up "
        "first. Otherwise refuse."
    ),
    "Preserve all unlisted behavior.": "Preserve every other case.",
    "Verify the selected action.": "Verify the action.",
}


class RenderedClosedWorldDecisionProjection(FrozenModel):
    """Target-visible closed-world rules with external semantic lineage."""

    renderer_id: Literal["codex-semantic-decision-runtime"] = CODEX_RUNTIME_V6_RENDERER_ID
    renderer_version: Literal["3.1.0"] = CODEX_RUNTIME_V6_RENDERER_VERSION
    target_family: Literal["codex"] = "codex"
    content: ExactRenderedText
    content_digest: Sha256Digest
    utf8_bytes: int = Field(ge=1)
    clause_digests: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def content_measurement_is_exact(self) -> Self:
        if self.content_digest != sha256_text(self.content):
            raise ValueError("closed-world content digest is inconsistent")
        if self.utf8_bytes != len(self.content.encode("utf-8")):
            raise ValueError("closed-world content byte count is inconsistent")
        return self


def build_codex_runtime_projection_v6(
    release: ExternalSemanticDecisionRelease,
    context: RuntimeProjectionContext,
) -> CanonicalRuntimeProjection:
    """Preserve semantic selection while making closed-world intent explicit."""

    prior = build_codex_runtime_projection_v5(release, context)
    clauses: list[RuntimeClause] = []
    for clause in prior.clauses:
        replacement = _TEXT_REWRITES.get(clause.text)
        if replacement is None:
            raise ValueError("closed-world renderer encountered an unsupported semantic clause")
        clauses.append(
            RuntimeClause(
                text=replacement,
                roles=clause.roles,
                source_artifact_refs=clause.source_artifact_refs,
            )
        )
    return CanonicalRuntimeProjection(
        external_release_digest=prior.external_release_digest,
        release_ref=prior.release_ref,
        context=prior.context,
        clauses=tuple(clauses),
        omitted_artifact_refs=prior.omitted_artifact_refs,
    )


def render_codex_runtime_projection_v6(
    projection: CanonicalRuntimeProjection,
) -> RenderedClosedWorldDecisionProjection:
    """Render the target-owned closed-world directive and natural rules."""

    if (
        ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        or projection.context.target_family != TargetKind.CODEX.value
    ):
        raise ValueError("Codex closed-world renderer requires a known Codex target")
    content = _HEADER + "".join(f"- {clause.text}\n" for clause in projection.clauses)
    return RenderedClosedWorldDecisionProjection(
        content=content,
        content_digest=sha256_text(content),
        utf8_bytes=len(content.encode("utf-8")),
        clause_digests=tuple(clause.content_digest for clause in projection.clauses),
    )


def build_runtime_projection_manifest_v6(
    *,
    release: ExternalSemanticDecisionRelease,
    projection: CanonicalRuntimeProjection,
    rendered: RenderedClosedWorldDecisionProjection,
) -> RuntimeProjectionManifest:
    """Bind every closed-world rule to exact governed evidence lineage."""

    if projection.external_release_digest != release.content_digest:
        raise ValueError("runtime v6 projection does not bind the supplied release")
    if projection != build_codex_runtime_projection_v6(release, projection.context):
        raise ValueError("runtime v6 projection is not canonical")
    if rendered != render_codex_runtime_projection_v6(projection):
        raise ValueError("runtime v6 rendered content drifted")
    bindings = {
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
                            bindings[source.record_id].content_digest
                            for source in clause.source_artifact_refs
                        }
                    )
                ),
            )
            for clause in projection.clauses
        ),
    )
