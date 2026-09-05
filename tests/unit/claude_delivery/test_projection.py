from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adaptation_compiler_lab.claude_delivery import render_claude_hook_projection
from adaptation_compiler_lab.domain import ArtifactRef, ReleaseRef
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
)
from adaptation_compiler_lab.targets.models import ScopeDimension

DIGEST = "sha256:" + "a" * 64


def _projection(target: str = "claude-code") -> CanonicalRuntimeProjection:
    source = ArtifactRef(record_id="artifact-one", record_version="1.0.0", content_digest=DIGEST)
    clauses = tuple(
        sorted(
            (
                RuntimeClause(
                    text="Prefer concrete names.",
                    roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                    source_artifact_refs=(source,),
                ),
                RuntimeClause(
                    text="Explain purpose before commands.",
                    roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                    source_artifact_refs=(source,),
                ),
            ),
            key=lambda item: item.content_digest,
        )
    )
    return CanonicalRuntimeProjection(
        external_release_digest=DIGEST,
        release_ref=ReleaseRef(
            record_id="release-one", record_version="1.0.0", content_digest=DIGEST
        ),
        context=RuntimeProjectionContext(
            known_dimensions=(
                ScopeDimension.PROJECT_IDS,
                ScopeDimension.SUBJECT_IDS,
                ScopeDimension.TARGET_FAMILIES,
            ),
            target_profile_id=target,
            subject_id="temper-owner",
            project_id="green-meadow",
            target_family=target,
            evaluated_at=datetime(2026, 8, 28, tzinfo=UTC),
        ),
        clauses=clauses,
    )


def test_claude_projection_is_compact_deterministic_and_target_bound() -> None:
    rendered = render_claude_hook_projection(_projection())
    assert rendered.content.count("Prefer concrete names.") == 1
    assert rendered.content.count("Explain purpose before commands.") == 1
    assert rendered.utf8_bytes == len(rendered.content.encode())
    assert rendered == render_claude_hook_projection(_projection())


def test_claude_projection_rejects_wrong_target_and_empty_delta() -> None:
    with pytest.raises(ValueError, match="known Claude Code"):
        render_claude_hook_projection(_projection("codex"))
    with pytest.raises(ValueError, match="cannot be empty"):
        render_claude_hook_projection(_projection().model_copy(update={"clauses": ()}))
