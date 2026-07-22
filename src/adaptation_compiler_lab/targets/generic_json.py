"""Generic canonical-JSON target pack renderer."""

from __future__ import annotations

from typing import Any

from adaptation_compiler_lab.targets.base import FileRenderer, canonical_json
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    TargetKind,
    TargetSurface,
)


def _artifact_document(artifact: ArtifactRenderProjection) -> dict[str, Any]:
    return {
        "artifact_ref": artifact.artifact_ref.model_dump(mode="json"),
        "artifact_type": artifact.artifact_type.value,
        "behavioral_contract": artifact.behavioral_contract.model_dump(mode="json"),
        "scope": artifact.scope.model_dump(mode="json"),
        "precedence": artifact.precedence,
        "review_at": artifact.review_at.isoformat() if artifact.review_at else None,
        "expires_at": artifact.expires_at.isoformat() if artifact.expires_at else None,
        "target_compatibility": list(artifact.target_compatibility),
        "claim_authorities": artifact.claim_authorities.model_dump(mode="json"),
        "privacy": {
            "sensitivity": artifact.privacy.sensitivity.value,
            "consent_basis": artifact.privacy.consent_basis,
            "permitted_uses": [item.value for item in artifact.privacy.permitted_uses],
            "review_state": artifact.privacy.review_state.value,
        },
        "evidence_links": {
            "supporting": [
                item.model_dump(mode="json") for item in artifact.evidence_links.supporting
            ],
            "contradicting": [
                item.model_dump(mode="json") for item in artifact.evidence_links.contradicting
            ],
            "scope_limiting": [
                item.model_dump(mode="json") for item in artifact.evidence_links.scope_limiting
            ],
        },
        "evaluation_case_refs": [
            item.model_dump(mode="json") for item in artifact.evaluation_cases
        ],
    }


class GenericJsonRenderer(FileRenderer):
    """Render the target-neutral behavioral view as canonical JSON."""

    renderer_id = "generic-json-renderer"
    target = TargetKind.GENERIC_JSON
    required_surfaces = frozenset({TargetSurface.JSON})

    def _render_content(
        self, artifacts: tuple[ArtifactRenderProjection, ...]
    ) -> tuple[dict[str, str], dict[str, tuple[str, ...]], frozenset[str]]:
        path = "adaptation-pack.json"
        content = canonical_json(
            {
                "schema_version": "1.0",
                "raw_evidence_included": False,
                "artifacts": [_artifact_document(item) for item in artifacts],
            }
        )
        paths: dict[str, tuple[str, ...]] = {
            item.artifact_ref.record_id: (path,) for item in artifacts
        }
        return {path: content}, paths, frozenset({path})
