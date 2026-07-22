"""Shared deterministic rendering, capability negotiation, and safe file output."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from adaptation_compiler_lab.domain.enums import (
    ArtifactKind,
    AuthorityClass,
    ClaimType,
    Partition,
    PrivacyReviewState,
    SensitivityClass,
)
from adaptation_compiler_lab.sanitization import ExportSafetyError, assert_export_safe
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.errors import RenderViolation, TargetRenderError
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    FileTargetCapabilityProfile,
    ReleaseRenderProjection,
    RenderedEntry,
    RenderedFile,
    RenderedPack,
    RenderOmission,
    ScopeDimension,
    TargetKind,
    TargetSurface,
)

RENDERER_VERSION: Final = "1.0.0"
MANIFEST_PATH: Final = ".adaptation-pack/manifest.json"

_SENSITIVITY_RANK: Final[dict[SensitivityClass, int]] = {
    SensitivityClass.PUBLIC: 0,
    SensitivityClass.INTERNAL: 1,
    SensitivityClass.PRIVATE: 2,
    SensitivityClass.CONFIDENTIAL: 3,
    SensitivityClass.RESTRICTED: 4,
    SensitivityClass.PROHIBITED_SECRET: 5,
}

_NORMATIVE_AUTHORITY: Final = frozenset(
    {AuthorityClass.USER_NORMATIVE, AuthorityClass.PROJECT_POLICY}
)
_DESCRIPTIVE_AUTHORITY: Final = _NORMATIVE_AUTHORITY | frozenset(
    {AuthorityClass.AUTHORIZED_EVALUATOR, AuthorityClass.OBSERVATIONAL}
)
_NORMATIVE_CLAIMS: Final = frozenset(
    {
        ClaimType.USER_PREFERENCE,
        ClaimType.USER_CORRECTION,
        ClaimType.USER_ACCEPTANCE,
        ClaimType.PROJECT_REQUIREMENT,
    }
)


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value deterministically with a final newline."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def sha256_text(content: str) -> str:
    """Return the canonical digest representation for UTF-8 text."""

    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def _is_instruction_artifact(kind: ArtifactKind) -> bool:
    return kind in {
        ArtifactKind.PREFERENCE,
        ArtifactKind.PROCEDURE,
        ArtifactKind.PROMPT_RULE,
        ArtifactKind.SKILL,
        ArtifactKind.TOOL_RECOMMENDATION,
    }


def _artifact_applies_to_target(artifact: ArtifactRenderProjection, target: TargetKind) -> bool:
    if target in {TargetKind.GENERIC_JSON, TargetKind.GENERIC_MARKDOWN}:
        return True
    families = set(artifact.scope.target_families)
    return not families or target.value in families


def _used_scope_dimensions(artifact: ArtifactRenderProjection) -> frozenset[ScopeDimension]:
    scope = artifact.scope
    dimensions: set[ScopeDimension] = {ScopeDimension.SUBJECT_IDS}
    for values, dimension in (
        (scope.workspace_ids, ScopeDimension.WORKSPACE_IDS),
        (scope.project_ids, ScopeDimension.PROJECT_IDS),
        (scope.repository_ids, ScopeDimension.REPOSITORY_IDS),
        (scope.task_classes, ScopeDimension.TASK_CLASSES),
        (scope.target_families, ScopeDimension.TARGET_FAMILIES),
        (scope.environment_ids, ScopeDimension.ENVIRONMENT_IDS),
        (scope.activation_conditions, ScopeDimension.ACTIVATION_CONDITIONS),
        (scope.exclusions, ScopeDimension.EXCLUSIONS),
    ):
        if values:
            dimensions.add(dimension)
    if (
        scope.valid_from is not None
        or scope.valid_until is not None
        or artifact.review_at is not None
        or artifact.expires_at is not None
    ):
        dimensions.add(ScopeDimension.VALIDITY_WINDOW)
    return frozenset(dimensions)


def _negotiate(
    release: ReleaseRenderProjection,
    profile: FileTargetCapabilityProfile,
    *,
    expected_target: TargetKind,
    required_surfaces: frozenset[TargetSurface],
) -> tuple[tuple[ArtifactRenderProjection, ...], tuple[RenderOmission, ...]]:
    violations: list[RenderViolation] = []
    omissions: list[RenderOmission] = []
    applicable: list[ArtifactRenderProjection] = []

    if profile.target is not expected_target:
        violations.append(
            RenderViolation(
                code="target_profile_mismatch",
                message=f"profile target {profile.target.value!r} does not match renderer target "
                f"{expected_target.value!r}",
            )
        )
    deployable_target = expected_target in {TargetKind.CODEX, TargetKind.CLAUDE_CODE}
    compatible_profile_ids = {
        profile.capabilities.profile_id,
        profile.capabilities.target_family,
    }
    if (
        deployable_target
        and release.target_compatibility
        and not compatible_profile_ids & set(release.target_compatibility)
    ):
        violations.append(
            RenderViolation(
                code="release_target_compatibility_mismatch",
                message="release target compatibility excludes this target profile",
            )
        )
    missing_surfaces = required_surfaces - profile.supported_surfaces
    if missing_surfaces:
        violations.append(
            RenderViolation(
                code="unsupported_surface",
                message="profile does not allow required surfaces: "
                + ", ".join(sorted(item.value for item in missing_surfaces)),
            )
        )
    if not profile.capabilities.supports_evidence_trace:
        violations.append(
            RenderViolation(
                code="evidence_trace_unsupported",
                message="target profile must preserve artifact-to-evidence traceability",
            )
        )
    if not profile.capabilities.supports_authority_labels:
        violations.append(
            RenderViolation(
                code="authority_labels_unsupported",
                message="target profile must preserve claim-specific authority labels",
            )
        )
    known_dimensions = {item.value for item in ScopeDimension}
    unknown_dimensions = set(profile.capabilities.supported_scope_dimensions) - known_dimensions
    if unknown_dimensions:
        violations.append(
            RenderViolation(
                code="unknown_scope_capability",
                message="profile declares unknown scope dimensions: "
                + ", ".join(sorted(unknown_dimensions)),
            )
        )
        supported_scope: set[ScopeDimension] = set()
    else:
        supported_scope = {
            ScopeDimension(item) for item in profile.capabilities.supported_scope_dimensions
        }

    for artifact in release.artifacts:
        if not _artifact_applies_to_target(artifact, expected_target):
            omissions.append(
                RenderOmission(
                    artifact_id=artifact.artifact_ref.record_id,
                    reason="artifact target-family scope excludes this target",
                )
            )
            continue
        applicable.append(artifact)
        if (
            deployable_target
            and artifact.target_compatibility
            and not compatible_profile_ids & set(artifact.target_compatibility)
        ):
            violations.append(
                RenderViolation(
                    code="artifact_target_compatibility_mismatch",
                    message="artifact target compatibility excludes this target profile",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if artifact.revoked:
            violations.append(
                RenderViolation(
                    code="revoked_artifact",
                    message="revoked artifacts cannot be rendered",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if Partition.HELD_OUT in artifact.source_partitions:
            violations.append(
                RenderViolation(
                    code="held_out_influence",
                    message="held-out material cannot influence a target pack",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if artifact.privacy.review_state is not PrivacyReviewState.APPROVED:
            violations.append(
                RenderViolation(
                    code="privacy_review_missing",
                    message="artifact lacks an approved privacy review",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if "target_delivery" not in {item.value for item in artifact.privacy.permitted_uses}:
            violations.append(
                RenderViolation(
                    code="target_delivery_not_permitted",
                    message="artifact permitted-use scope excludes target delivery",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if (
            _SENSITIVITY_RANK[artifact.privacy.sensitivity]
            > _SENSITIVITY_RANK[profile.capabilities.maximum_sensitivity]
        ):
            violations.append(
                RenderViolation(
                    code="privacy_ceiling_exceeded",
                    message=f"artifact sensitivity {artifact.privacy.sensitivity.value!r} "
                    "exceeds profile ceiling",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        normative_support = False
        for claim_authority in artifact.claim_authorities.entries:
            allowed_authorities = (
                _NORMATIVE_AUTHORITY
                if claim_authority.claim_type in _NORMATIVE_CLAIMS
                else _DESCRIPTIVE_AUTHORITY
            )
            if claim_authority.authority_class not in allowed_authorities:
                violations.append(
                    RenderViolation(
                        code="untrusted_instruction_authority",
                        message=f"authority {claim_authority.authority_class.value!r} cannot "
                        f"support claim {claim_authority.claim_type.value!r}",
                        artifact_id=artifact.artifact_ref.record_id,
                    )
                )
            if (
                claim_authority.claim_type in _NORMATIVE_CLAIMS
                and claim_authority.authority_class in _NORMATIVE_AUTHORITY
            ):
                normative_support = True
        if _is_instruction_artifact(artifact.artifact_type) and not normative_support:
            violations.append(
                RenderViolation(
                    code="normative_authority_missing",
                    message="instruction artifact lacks claim-specific normative authority",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if artifact.artifact_type not in profile.capabilities.supported_artifact_kinds:
            violations.append(
                RenderViolation(
                    code="unsupported_artifact_type",
                    message=f"profile cannot represent {artifact.artifact_type.value!r}",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        unsupported_scope = _used_scope_dimensions(artifact) - supported_scope
        if unsupported_scope:
            violations.append(
                RenderViolation(
                    code="unsupported_scope",
                    message="profile cannot preserve scope dimensions: "
                    + ", ".join(sorted(item.value for item in unsupported_scope)),
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if artifact.precedence != 0 and not profile.capabilities.supports_precedence:
            violations.append(
                RenderViolation(
                    code="precedence_loss",
                    message="profile cannot preserve explicit artifact precedence",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )
        if (
            artifact.expires_at is not None or artifact.review_at is not None
        ) and not profile.capabilities.supports_expiry:
            violations.append(
                RenderViolation(
                    code="expiry_loss",
                    message="profile cannot preserve artifact expiry",
                    artifact_id=artifact.artifact_ref.record_id,
                )
            )

    if len(applicable) > profile.max_entries:
        violations.append(
            RenderViolation(
                code="entry_limit_exceeded",
                message=f"{len(applicable)} applicable artifacts exceed limit "
                f"{profile.max_entries}",
            )
        )
    if violations:
        raise TargetRenderError(tuple(violations))
    ordered = tuple(
        sorted(
            applicable,
            key=lambda item: (
                item.precedence,
                item.artifact_ref.record_id,
                item.artifact_ref.record_version,
            ),
        )
    )
    return ordered, tuple(sorted(omissions, key=lambda item: item.artifact_id))


def _entry(artifact: ArtifactRenderProjection, paths: Sequence[str]) -> RenderedEntry:
    return RenderedEntry(
        artifact_id=artifact.artifact_ref.record_id,
        artifact_version=artifact.artifact_ref.record_version,
        artifact_digest=artifact.artifact_ref.content_digest,
        paths=tuple(paths),
        supporting_evidence_ids=tuple(
            item.record_id for item in artifact.evidence_links.supporting
        ),
        contradicting_evidence_ids=tuple(
            item.record_id for item in artifact.evidence_links.contradicting
        ),
        scope_limiting_evidence_ids=tuple(
            item.record_id for item in artifact.evidence_links.scope_limiting
        ),
        authority_digest=canonical_digest(artifact.claim_authorities),
    )


class FileRenderer(ABC):
    """Base for pure renderers that produce files but never invoke an agent."""

    renderer_id: str
    target: TargetKind
    required_surfaces: frozenset[TargetSurface]

    def render(
        self, release: ReleaseRenderProjection, profile: FileTargetCapabilityProfile
    ) -> RenderedPack:
        release = ReleaseRenderProjection.model_validate(release.model_dump(mode="python"))
        profile = FileTargetCapabilityProfile.model_validate(profile.model_dump(mode="python"))
        artifacts, omissions = _negotiate(
            release,
            profile,
            expected_target=self.target,
            required_surfaces=self.required_surfaces,
        )
        content_by_path, artifact_paths, primary_paths = self._render_content(artifacts)
        entries = tuple(
            _entry(item, artifact_paths[item.artifact_ref.record_id]) for item in artifacts
        )

        primary_bytes = sum(
            len(content_by_path[path].encode("utf-8")) for path in sorted(primary_paths)
        )
        if primary_bytes > profile.max_primary_instruction_bytes:
            raise TargetRenderError(
                (
                    RenderViolation(
                        code="primary_instruction_limit_exceeded",
                        message=f"{primary_bytes} bytes exceed limit "
                        f"{profile.max_primary_instruction_bytes}; truncation is forbidden",
                    ),
                )
            )
        primary_lines = sum(content_by_path[path].count("\n") for path in primary_paths)
        if (
            profile.max_primary_instruction_lines is not None
            and primary_lines > profile.max_primary_instruction_lines
        ):
            raise TargetRenderError(
                (
                    RenderViolation(
                        code="primary_instruction_line_limit_exceeded",
                        message=f"{primary_lines} lines exceed recommended limit "
                        f"{profile.max_primary_instruction_lines}; truncation is forbidden",
                    ),
                )
            )

        manifest = self._manifest(release, profile, content_by_path, entries, omissions)
        if MANIFEST_PATH in content_by_path:
            raise RuntimeError("renderer attempted to replace the reserved pack manifest")
        content_by_path[MANIFEST_PATH] = canonical_json(manifest)
        for path, content in sorted(content_by_path.items()):
            try:
                assert_export_safe(content, label=path)
            except ExportSafetyError as error:
                raise TargetRenderError(
                    (
                        RenderViolation(
                            code="secret_like_content",
                            message=str(error),
                        ),
                    )
                ) from error
        files = tuple(
            RenderedFile(
                path=path,
                content=content_by_path[path],
                content_digest=sha256_text(content_by_path[path]),
            )
            for path in sorted(content_by_path)
        )
        total_bytes = sum(len(item.content.encode("utf-8")) for item in files)
        if total_bytes > profile.max_total_bytes:
            raise TargetRenderError(
                (
                    RenderViolation(
                        code="pack_size_limit_exceeded",
                        message=f"{total_bytes} bytes exceed limit {profile.max_total_bytes}; "
                        "truncation is forbidden",
                    ),
                )
            )
        pack_digest = sha256_text(
            canonical_json(
                [{"path": item.path, "content_digest": item.content_digest} for item in files]
            )
        )
        return RenderedPack(
            renderer_id=self.renderer_id,
            renderer_version=RENDERER_VERSION,
            target_profile_id=profile.capabilities.profile_id,
            target_profile_version=profile.capabilities.profile_version,
            release_id=release.release_ref.record_id,
            release_version=release.release_version,
            release_digest=release.release_ref.content_digest,
            files=files,
            entries=entries,
            omissions=omissions,
            pack_digest=pack_digest,
            total_bytes=total_bytes,
        )

    @abstractmethod
    def _render_content(
        self, artifacts: tuple[ArtifactRenderProjection, ...]
    ) -> tuple[dict[str, str], dict[str, tuple[str, ...]], frozenset[str]]:
        """Return content, artifact-to-path trace, and primary instruction paths."""

    def _manifest(
        self,
        release: ReleaseRenderProjection,
        profile: FileTargetCapabilityProfile,
        content_by_path: Mapping[str, str],
        entries: tuple[RenderedEntry, ...],
        omissions: tuple[RenderOmission, ...],
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "renderer": {"id": self.renderer_id, "version": RENDERER_VERSION},
            "target_profile": {
                "id": profile.capabilities.profile_id,
                "version": profile.capabilities.profile_version,
                "target": profile.target.value,
                "documentation_uri": profile.documentation_uri,
                "documentation_checked_on": profile.documentation_checked_on,
            },
            "release": {
                "id": release.release_ref.record_id,
                "version": release.release_version,
                "digest": release.release_ref.content_digest,
                "policy_version": release.policy_version,
                "target_compatibility": list(release.target_compatibility),
            },
            "files": [
                {"path": path, "content_digest": sha256_text(content_by_path[path])}
                for path in sorted(content_by_path)
            ],
            "entries": [item.model_dump(mode="json") for item in entries],
            "omissions": [item.model_dump(mode="json") for item in omissions],
            "losses": [],
            "raw_evidence_included": False,
        }


def render_target_pack(
    release: ReleaseRenderProjection, profile: FileTargetCapabilityProfile
) -> RenderedPack:
    """Dispatch to the renderer named by an explicit capability profile."""

    from adaptation_compiler_lab.targets.claude_code import ClaudeCodeRenderer
    from adaptation_compiler_lab.targets.codex import CodexRenderer
    from adaptation_compiler_lab.targets.generic_json import GenericJsonRenderer
    from adaptation_compiler_lab.targets.generic_markdown import GenericMarkdownRenderer

    renderers: dict[TargetKind, FileRenderer] = {
        TargetKind.GENERIC_JSON: GenericJsonRenderer(),
        TargetKind.GENERIC_MARKDOWN: GenericMarkdownRenderer(),
        TargetKind.CODEX: CodexRenderer(),
        TargetKind.CLAUDE_CODE: ClaudeCodeRenderer(),
    }
    return renderers[profile.target].render(release, profile)


def write_rendered_pack(pack: RenderedPack, output_directory: Path) -> tuple[Path, ...]:
    """Materialize a pack into a new or empty directory without installing it."""

    if len({item.path for item in pack.files}) != len(pack.files):
        raise ValueError("rendered pack contains duplicate file paths")
    total_bytes = 0
    for rendered_file in pack.files:
        if rendered_file.content_digest != sha256_text(rendered_file.content):
            raise ValueError("rendered file digest does not match its content")
        try:
            assert_export_safe(rendered_file.content, label=rendered_file.path)
        except ExportSafetyError as error:
            raise ValueError(str(error)) from error
        total_bytes += len(rendered_file.content.encode("utf-8"))
    expected_pack_digest = sha256_text(
        canonical_json(
            [
                {"path": item.path, "content_digest": item.content_digest}
                for item in sorted(pack.files, key=lambda item: item.path)
            ]
        )
    )
    if pack.total_bytes != total_bytes or pack.pack_digest != expected_pack_digest:
        raise ValueError("rendered pack aggregate metadata does not match its files")
    root = output_directory.resolve()
    if output_directory.exists() and any(output_directory.iterdir()):
        raise FileExistsError("target pack output directory must be new or empty")

    destinations: list[tuple[RenderedFile, Path]] = []
    for rendered_file in pack.files:
        destination = (root / Path(rendered_file.path)).resolve()
        if root != destination and root not in destination.parents:
            raise ValueError("rendered path escapes the output directory")
        destinations.append((rendered_file, destination))

    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for rendered_file, destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered_file.content)
        written.append(destination)
    return tuple(written)


def scope_lines(artifact: ArtifactRenderProjection) -> list[str]:
    """Render every non-empty scope constraint explicitly and deterministically."""

    lines: list[str] = []
    for label, values in (
        ("Subjects", artifact.scope.subject_ids),
        ("Workspaces", artifact.scope.workspace_ids),
        ("Projects", artifact.scope.project_ids),
        ("Repositories", artifact.scope.repository_ids),
        ("Task classes", artifact.scope.task_classes),
        ("Target families", artifact.scope.target_families),
        ("Environments", artifact.scope.environment_ids),
        ("Activation conditions", artifact.scope.activation_conditions),
        ("Exclusions", artifact.scope.exclusions),
    ):
        if values:
            lines.append(f"- {label}: " + "; ".join(values))
    if not lines:
        lines.append("- Scope: all contexts admitted by the containing release")
    lines.append(f"- Precedence: {artifact.precedence}")
    if artifact.scope.valid_from is not None:
        lines.append(f"- Valid from: {artifact.scope.valid_from.isoformat()}")
    if artifact.scope.valid_until is not None:
        lines.append(f"- Scope valid until: {artifact.scope.valid_until.isoformat()}")
    if artifact.review_at is not None:
        lines.append(f"- Review by: {artifact.review_at.isoformat()}")
    if artifact.expires_at is not None:
        lines.append(f"- Expires at: {artifact.expires_at.isoformat()}")
    if artifact.target_compatibility:
        lines.append("- Compatible target profiles: " + "; ".join(artifact.target_compatibility))
    return lines


def artifact_trace_lines(artifact: ArtifactRenderProjection) -> list[str]:
    """Render opaque lineage identifiers, never evidence payloads."""

    lines = [
        "- Supporting evidence IDs: "
        + ", ".join(item.record_id for item in artifact.evidence_links.supporting),
        "- Evaluation case IDs: " + ", ".join(item.record_id for item in artifact.evaluation_cases),
    ]
    if artifact.evidence_links.contradicting:
        lines.append(
            "- Contradicting evidence IDs: "
            + ", ".join(item.record_id for item in artifact.evidence_links.contradicting)
        )
    if artifact.evidence_links.scope_limiting:
        lines.append(
            "- Scope-limiting evidence IDs: "
            + ", ".join(item.record_id for item in artifact.evidence_links.scope_limiting)
        )
    lines.append("- Claim-specific authority:")
    lines.extend(
        "  - "
        f"{item.claim_type.value}: {item.authority_class.value} "
        f"(evidence: {', '.join(ref.record_id for ref in item.evidence_refs)})"
        for item in artifact.claim_authorities.entries
    )
    return lines


def markdown_artifact(artifact: ArtifactRenderProjection, *, heading_level: int = 2) -> str:
    """Render one portable artifact as inspectable Markdown."""

    prefix = "#" * heading_level
    lines = [
        f"{prefix} {artifact.behavioral_contract.intent}",
        "",
        f"Type: `{artifact.artifact_type.value}`  ",
        f"Artifact: `{artifact.artifact_ref.record_id}@{artifact.artifact_ref.record_version}`",
        "",
        f"{prefix}# Behavioral contract",
        "",
        *[f"- {item}" for item in artifact.behavioral_contract.required_behaviors],
        "",
        f"{prefix}# Verification requirements",
        "",
        *[f"- {item}" for item in artifact.behavioral_contract.verification_requirements],
        "",
        f"{prefix}# Scope and precedence",
        "",
        *scope_lines(artifact),
        "",
        f"{prefix}# Provenance trace",
        "",
        *artifact_trace_lines(artifact),
    ]
    if artifact.artifact_type is ArtifactKind.TOOL_RECOMMENDATION:
        lines.extend(
            [
                "",
                f"{prefix}# Safety",
                "",
                "This is advisory only. Do not install, enable, authorize, or execute a tool "
                "without a current explicit user instruction.",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
