"""Versioned default file-target capability profiles."""

from __future__ import annotations

from adaptation_compiler_lab.domain.enums import ArtifactKind, SensitivityClass
from adaptation_compiler_lab.domain.values import TargetCapabilityProfile
from adaptation_compiler_lab.targets.models import (
    FileTargetCapabilityProfile,
    ScopeDimension,
    TargetKind,
    TargetSurface,
)

_ALL_ARTIFACT_KINDS = tuple(sorted(ArtifactKind, key=lambda item: item.value))
_ALL_SCOPE_DIMENSIONS = tuple(sorted(item.value for item in ScopeDimension))


def _canonical_profile(profile_id: str, target: TargetKind) -> TargetCapabilityProfile:
    return TargetCapabilityProfile(
        profile_id=profile_id,
        profile_version="1.0.0",
        target_family=target.value,
        supported_artifact_kinds=_ALL_ARTIFACT_KINDS,
        supported_scope_dimensions=_ALL_SCOPE_DIMENSIONS,
        supports_precedence=True,
        supports_evidence_trace=True,
        supports_authority_labels=True,
        supports_expiry=True,
        max_context_tokens=32_000,
        maximum_sensitivity=SensitivityClass.PRIVATE,
    )


def default_target_profile(target: TargetKind) -> FileTargetCapabilityProfile:
    """Return a conservative profile for an implemented file surface."""

    if target is TargetKind.GENERIC_JSON:
        capabilities = _canonical_profile("generic-json-files", target)
        return FileTargetCapabilityProfile(
            capabilities=capabilities,
            target=target,
            documentation_uri="https://www.rfc-editor.org/rfc/rfc8259",
            documentation_checked_on="2026-07-22",
            supported_surfaces=frozenset({TargetSurface.JSON}),
            max_entries=1_000,
            max_total_bytes=4_000_000,
            max_primary_instruction_bytes=4_000_000,
        )
    if target is TargetKind.GENERIC_MARKDOWN:
        capabilities = _canonical_profile("generic-markdown-files", target)
        return FileTargetCapabilityProfile(
            capabilities=capabilities,
            target=target,
            documentation_uri="https://spec.commonmark.org/0.31.2/",
            documentation_checked_on="2026-07-22",
            supported_surfaces=frozenset({TargetSurface.MARKDOWN}),
            max_entries=1_000,
            max_total_bytes=4_000_000,
            max_primary_instruction_bytes=4_000_000,
        )
    if target is TargetKind.CODEX:
        capabilities = _canonical_profile("codex-file-surfaces", target)
        return FileTargetCapabilityProfile(
            capabilities=capabilities,
            target=target,
            documentation_uri="https://developers.openai.com/codex/codex-manual.md",
            documentation_checked_on="2026-07-22",
            supported_surfaces=frozenset({TargetSurface.AGENTS_MD, TargetSurface.AGENT_SKILL}),
            max_entries=256,
            max_total_bytes=1_000_000,
            max_primary_instruction_bytes=32_768,
        )
    capabilities = _canonical_profile("claude-code-file-surfaces", target)
    return FileTargetCapabilityProfile(
        capabilities=capabilities,
        target=target,
        documentation_uri="https://code.claude.com/docs/en/features-overview",
        documentation_checked_on="2026-07-22",
        supported_surfaces=frozenset(
            {
                TargetSurface.CLAUDE_MD,
                TargetSurface.CLAUDE_RULE,
                TargetSurface.CLAUDE_SKILL,
            }
        ),
        max_entries=256,
        max_total_bytes=1_000_000,
        max_primary_instruction_bytes=64_000,
        max_primary_instruction_lines=200,
    )
