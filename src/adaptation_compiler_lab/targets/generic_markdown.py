"""Generic human-readable Markdown target pack renderer."""

from __future__ import annotations

from adaptation_compiler_lab.targets.base import FileRenderer, markdown_artifact
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    TargetKind,
    TargetSurface,
)


class GenericMarkdownRenderer(FileRenderer):
    """Render all portable artifacts into one inspectable Markdown file."""

    renderer_id = "generic-markdown-renderer"
    target = TargetKind.GENERIC_MARKDOWN
    required_surfaces = frozenset({TargetSurface.MARKDOWN})

    def _render_content(
        self, artifacts: tuple[ArtifactRenderProjection, ...]
    ) -> tuple[dict[str, str], dict[str, tuple[str, ...]], frozenset[str]]:
        path = "ADAPTATION.md"
        sections = [
            "# Compiled adaptation pack",
            "",
            "This file contains reviewed behavioral artifacts. Explicit current user instructions "
            "and applicable project policy take precedence. Evidence identifiers are audit links; "
            "raw evidence is not included.",
        ]
        for artifact in artifacts:
            sections.extend(["", markdown_artifact(artifact).rstrip()])
        content = "\n".join(sections).rstrip() + "\n"
        paths: dict[str, tuple[str, ...]] = {
            item.artifact_ref.record_id: (path,) for item in artifacts
        }
        return {path: content}, paths, frozenset({path})
