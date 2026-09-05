"""Compact target-specific renderer for cached Claude hook context."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.runtime.models import CanonicalRuntimeProjection
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind


class ClaudeHookRenderedProjectionV1(FrozenModel):
    """Small approved delta inserted as ``additionalContext`` without file writeback."""

    renderer_id: Literal["claude-hook-runtime"] = "claude-hook-runtime"
    renderer_version: Literal["1.0.0"] = "1.0.0"
    content: str = Field(min_length=1, max_length=10_000)
    content_digest: Sha256Digest
    utf8_bytes: int = Field(gt=0, le=12_000)
    clause_digests: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def measurements_are_exact(self) -> Self:
        if self.content_digest != sha256_text(self.content):
            raise ValueError("Claude hook projection digest is inconsistent")
        if self.utf8_bytes != len(self.content.encode("utf-8")):
            raise ValueError("Claude hook projection byte count is inconsistent")
        if self.clause_digests != tuple(sorted(set(self.clause_digests))):
            raise ValueError("Claude hook projection clauses must be sorted and unique")
        return self


def render_claude_hook_projection(
    projection: CanonicalRuntimeProjection,
) -> ClaudeHookRenderedProjectionV1:
    """Render only the relevant governed delta for an exact Claude target context."""

    if (
        ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        or projection.context.target_family != TargetKind.CLAUDE_CODE.value
    ):
        raise ValueError("Claude hook renderer requires a known Claude Code target")
    if not projection.clauses:
        raise ValueError("Claude hook projection cannot be empty")
    clauses = tuple(sorted(projection.clauses, key=lambda item: item.content_digest))
    content = (
        "Applicable approved Temper preferences for this project. Current user instructions "
        "and project policy take precedence:\n" + "".join(f"- {item.text}\n" for item in clauses)
    )
    return ClaudeHookRenderedProjectionV1(
        content=content,
        content_digest=sha256_text(content),
        utf8_bytes=len(content.encode("utf-8")),
        clause_digests=tuple(item.content_digest for item in clauses),
    )
