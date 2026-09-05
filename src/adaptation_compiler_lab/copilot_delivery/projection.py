"""Compact native-aware runtime projection for GitHub Copilot CLI."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.copilot_delivery.models import (
    MAX_COPILOT_PROJECTION_UTF8_BYTES,
    CopilotProjectionManifestV1,
)
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.instruction_environment.models import InstructionDeltaPlanV1
from adaptation_compiler_lab.instruction_environment.resolver import apply_instruction_environment
from adaptation_compiler_lab.runtime.models import CanonicalRuntimeProjection
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.models import ScopeDimension

COPILOT_CLI_TARGET_FAMILY = "copilot-cli"


class CopilotHookRenderedProjectionV1(FrozenModel):
    """Small approved delta appended only to Copilot's model-facing prompt."""

    renderer_id: Literal["copilot-cli-hook-runtime"] = "copilot-cli-hook-runtime"
    renderer_version: Literal["1.0.0"] = "1.0.0"
    content: str = Field(min_length=1, max_length=MAX_COPILOT_PROJECTION_UTF8_BYTES)
    content_digest: Sha256Digest
    utf8_bytes: int = Field(gt=0, le=MAX_COPILOT_PROJECTION_UTF8_BYTES)
    clause_digests: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def measurements_are_exact(self) -> Self:
        if self.content_digest != sha256_text(self.content):
            raise ValueError("Copilot hook projection digest is inconsistent")
        if self.utf8_bytes != len(self.content.encode("utf-8")):
            raise ValueError("Copilot hook projection byte count is inconsistent")
        if self.clause_digests != tuple(sorted(set(self.clause_digests))):
            raise ValueError("Copilot hook projection clauses must be sorted and unique")
        return self


def render_copilot_hook_projection(
    projection: CanonicalRuntimeProjection,
) -> CopilotHookRenderedProjectionV1:
    """Render only the approved delta for an exact Copilot CLI context."""

    if (
        ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        or projection.context.target_family != COPILOT_CLI_TARGET_FAMILY
    ):
        raise ValueError("Copilot hook renderer requires a known Copilot CLI target")
    if not projection.clauses:
        raise ValueError("Copilot hook projection cannot be empty")
    clauses = tuple(sorted(projection.clauses, key=lambda item: item.content_digest))
    content = (
        "Applicable approved Temper preferences for this project. Current user instructions "
        "and project policy take precedence:\n" + "".join(f"- {item.text}\n" for item in clauses)
    )
    return CopilotHookRenderedProjectionV1(
        content=content,
        content_digest=sha256_text(content),
        utf8_bytes=len(content.encode("utf-8")),
        clause_digests=tuple(item.content_digest for item in clauses),
    )


def build_copilot_projection_manifest(
    *,
    subject_id: str,
    projection: CanonicalRuntimeProjection,
    delta_plan: InstructionDeltaPlanV1,
    rendered: CopilotHookRenderedProjectionV1,
    created_at: datetime,
    target_authorization_digest: Sha256Digest | None = None,
) -> CopilotProjectionManifestV1:
    """Bind one rendered Copilot delta to release, scope, and native coverage."""

    if (
        projection.context.subject_id != subject_id
        or projection.context.project_id != delta_plan.project_id
    ):
        raise ValueError("Copilot projection manifest crossed its owner or project")
    delta = apply_instruction_environment(projection, delta_plan)
    if not delta.clauses or render_copilot_hook_projection(delta) != rendered:
        raise ValueError("Copilot rendered projection does not match its instruction delta")
    if rendered.clause_digests != tuple(sorted(delta_plan.included_temper_clause_digests)):
        raise ValueError("Copilot rendered clauses do not match the instruction delta")
    return CopilotProjectionManifestV1(
        subject_id=subject_id,
        project_id=delta_plan.project_id,
        external_release_digest=projection.external_release_digest,
        target_authorization_digest=target_authorization_digest,
        canonical_projection_digest=projection.content_digest,
        delta_projection_digest=delta.content_digest,
        instruction_environment_digest=delta_plan.environment_digest,
        native_source_chain_digest=delta_plan.source_chain_digest,
        included_clause_digests=delta_plan.included_temper_clause_digests,
        omitted_clause_digests=delta_plan.omitted_temper_clause_digests,
        blocked_clause_digests=delta_plan.blocked_temper_clause_digests,
        relation_digests=tuple(sorted(canonical_digest(item) for item in delta_plan.relations)),
        unresolved_conflict_ids=tuple(sorted(item.conflict_id for item in delta_plan.conflicts)),
        rendered_content_digest=rendered.content_digest,
        rendered_utf8_bytes=rendered.utf8_bytes,
        fully_optimized=delta_plan.fully_optimized,
        created_at=created_at,
    )
