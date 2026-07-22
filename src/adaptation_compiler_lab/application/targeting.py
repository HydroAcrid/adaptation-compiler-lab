"""Fail-closed application services for release projection and target-pack validation.

The renderer boundary deliberately receives resolved promoted artifacts rather than raw
``Evidence`` payloads.  This module is the only bridge between the immutable domain graph and
that boundary, and between deterministic rendered files and the domain ``TargetPack`` manifest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from typing import cast

from pydantic import BaseModel, Field, ValidationError

from adaptation_compiler_lab.domain import (
    ActorRef,
    AnyRecordRef,
    Artifact,
    ArtifactKind,
    ArtifactRef,
    EvaluationCase,
    EvaluationCaseRef,
    Evidence,
    EvidenceRef,
    FrozenModel,
    Identifier,
    LessonCandidate,
    LossMateriality,
    Outcome,
    Partition,
    PermittedUse,
    PrivacyContext,
    PrivacyReviewState,
    Release,
    ReleaseRef,
    RenderingLoss,
    SemVer,
    SensitivityClass,
    Sha256Digest,
    TargetPack,
    TargetPackState,
    TaskRecord,
    UtcDateTime,
    VersionedRecord,
)
from adaptation_compiler_lab.domain import RenderedEntry as DomainRenderedEntry
from adaptation_compiler_lab.domain.references import ExactRecordRef
from adaptation_compiler_lab.domain.values import record_ref_key
from adaptation_compiler_lab.provenance import (
    RecordIndex,
    index_records,
    resolve_reference,
    validate_release_membership,
    validate_target_pack,
)
from adaptation_compiler_lab.release.gates import evaluate_release_gates
from adaptation_compiler_lab.release.proposals import propose_release_candidate
from adaptation_compiler_lab.sanitization import (
    ExportSafetyError,
    assert_export_safe,
    is_sensitive_path,
)
from adaptation_compiler_lab.serialization import canonical_digest, record_ref
from adaptation_compiler_lab.targets.base import (
    MANIFEST_PATH,
    RENDERER_VERSION,
    sha256_text,
)
from adaptation_compiler_lab.targets.base import canonical_json as target_canonical_json
from adaptation_compiler_lab.targets.codex import safe_slug
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    FileTargetCapabilityProfile,
    ReleaseRenderProjection,
    RenderedPack,
    RenderOmission,
    ScopeDimension,
    TargetKind,
    TargetSurface,
)


class TargetingError(ValueError):
    """An exact release or rendered pack could not cross a targeting boundary safely."""


class TargetPackBuildContext(FrozenModel):
    """Attributable metadata supplied explicitly when a domain target pack is built."""

    record_id: Identifier
    record_version: SemVer
    created_at: UtcDateTime
    created_by: ActorRef
    policy_version: SemVer
    privacy: PrivacyContext
    context_token_cost: int = Field(default=0, ge=0)
    runtime_selector_digest: Sha256Digest | None = None


_DOMAIN_RECORD_TYPES: tuple[type[VersionedRecord], ...] = (
    TaskRecord,
    Outcome,
    Evidence,
    EvaluationCase,
    LessonCandidate,
    Artifact,
    Release,
    TargetPack,
)

_SENSITIVITY_RANK: dict[SensitivityClass, int] = {
    SensitivityClass.PUBLIC: 0,
    SensitivityClass.INTERNAL: 1,
    SensitivityClass.PRIVATE: 2,
    SensitivityClass.CONFIDENTIAL: 3,
    SensitivityClass.RESTRICTED: 4,
    SensitivityClass.PROHIBITED_SECRET: 5,
}

_RENDERER_IDS: dict[TargetKind, str] = {
    TargetKind.GENERIC_JSON: "generic-json-renderer",
    TargetKind.GENERIC_MARKDOWN: "generic-markdown-renderer",
    TargetKind.CODEX: "codex-file-renderer",
    TargetKind.CLAUDE_CODE: "claude-code-file-renderer",
}

_REQUIRED_SURFACES: dict[TargetKind, frozenset[TargetSurface]] = {
    TargetKind.GENERIC_JSON: frozenset({TargetSurface.JSON}),
    TargetKind.GENERIC_MARKDOWN: frozenset({TargetSurface.MARKDOWN}),
    TargetKind.CODEX: frozenset({TargetSurface.AGENTS_MD, TargetSurface.AGENT_SKILL}),
    TargetKind.CLAUDE_CODE: frozenset(
        {TargetSurface.CLAUDE_MD, TargetSurface.CLAUDE_RULE, TargetSurface.CLAUDE_SKILL}
    ),
}


def _strict[ModelT: BaseModel](value: ModelT, model_type: type[ModelT], *, label: str) -> ModelT:
    """Rerun validators, including for instances made with copy/construct escape hatches."""

    try:
        return model_type.model_validate(value.model_dump(mode="python", round_trip=True))
    except (TypeError, ValueError, ValidationError) as error:
        raise TargetingError(f"{label} failed strict validation: {error}") from error


def _strict_record(record: VersionedRecord) -> VersionedRecord:
    for model_type in _DOMAIN_RECORD_TYPES:
        if type(record) is model_type:
            try:
                return model_type.model_validate(record.model_dump(mode="python", round_trip=True))
            except (TypeError, ValueError, ValidationError) as error:
                raise TargetingError(
                    f"domain record {record.record_id!r} failed strict validation: {error}"
                ) from error
    raise TargetingError(f"unsupported domain record type: {type(record).__name__}")


def _strict_records(records: Iterable[VersionedRecord]) -> tuple[VersionedRecord, ...]:
    materialized = tuple(_strict_record(record) for record in records)
    try:
        index_records(materialized)
    except ValueError as error:
        raise TargetingError(f"domain record set is ambiguous: {error}") from error
    return materialized


def _resolve_exact[RecordT: VersionedRecord](
    index: RecordIndex,
    reference: AnyRecordRef | ExactRecordRef,
    expected_type: type[RecordT],
    *,
    relation: str,
) -> RecordT:
    resolved = resolve_reference(index, cast(AnyRecordRef, reference))
    if not isinstance(resolved, expected_type):
        raise TargetingError(
            f"{relation} is unresolved, missing, or digest-mismatched: "
            f"{reference.record_type.value}:{reference.record_id}@{reference.record_version}"
        )
    return resolved


def _decision_error(prefix: str, messages: Iterable[str]) -> TargetingError:
    details = "; ".join(sorted(set(messages)))
    return TargetingError(f"{prefix}: {details}")


class _ProjectionSources:
    """Resolve the complete construction-side source graph for one artifact."""

    def __init__(self, index: RecordIndex) -> None:
        self._index = index
        self._visited: set[tuple[str, str, str, str]] = set()
        self._partitions: set[Partition] = set()
        self._cases: dict[tuple[str, str, str, str], EvaluationCaseRef] = {}

    @property
    def partitions(self) -> tuple[Partition, ...]:
        ordered = tuple(sorted(self._partitions, key=lambda item: item.value))
        if not ordered:
            raise TargetingError("artifact has no resolvable source partition")
        if Partition.HELD_OUT in ordered:
            raise TargetingError("held-out material cannot influence a render projection")
        return ordered

    @property
    def evaluation_cases(self) -> tuple[EvaluationCaseRef, ...]:
        ordered = tuple(self._cases[key] for key in sorted(self._cases))
        if not ordered:
            raise TargetingError("artifact has no resolvable evaluation case")
        return ordered

    def add_artifact(self, artifact: Artifact) -> None:
        for reference in (
            *artifact.evidence_links.supporting,
            *artifact.evidence_links.contradicting,
            *artifact.evidence_links.scope_limiting,
            *artifact.source_candidate_refs,
        ):
            self.visit(cast(AnyRecordRef, reference))
        for attestation in artifact.evaluation_attestations:
            self._add_partition(attestation.partition, relation="artifact attestation")
            self.visit(cast(AnyRecordRef, attestation.case_ref))

    def add_release_attestation(self, case_ref: EvaluationCaseRef, partition: Partition) -> None:
        self._add_partition(partition, relation="release attestation")
        self.visit(cast(AnyRecordRef, case_ref))

    def _add_partition(self, partition: Partition, *, relation: str) -> None:
        if partition is Partition.HELD_OUT:
            raise TargetingError(f"held-out {relation} cannot influence a render projection")
        self._partitions.add(partition)

    def visit(self, reference: AnyRecordRef) -> None:
        key = record_ref_key(reference)
        if key in self._visited:
            return
        self._visited.add(key)
        resolved = resolve_reference(self._index, reference)
        if resolved is None:
            raise TargetingError(
                "construction source is unresolved, missing, or digest-mismatched: "
                f"{reference.record_type.value}:{reference.record_id}@"
                f"{reference.record_version}"
            )
        if isinstance(resolved, Evidence):
            self._visit_evidence(resolved)
        elif isinstance(resolved, TaskRecord):
            self._visit_task(resolved)
        elif isinstance(resolved, Outcome):
            self._visit_outcome(resolved)
        elif isinstance(resolved, EvaluationCase):
            self._visit_case(resolved)
        elif isinstance(resolved, LessonCandidate):
            self._visit_candidate(resolved)
        else:
            raise TargetingError(
                f"unsupported construction provenance record: {resolved.record_type.value}"
            )

    def _visit_evidence(self, evidence: Evidence) -> None:
        self._add_partition(evidence.partition, relation="evidence")
        if evidence.privacy.sensitivity is SensitivityClass.PROHIBITED_SECRET:
            raise TargetingError("secret-classified evidence cannot influence a render projection")
        for reference in evidence.parent_evidence_refs:
            self.visit(cast(AnyRecordRef, reference))
        if evidence.task_ref is not None:
            self.visit(cast(AnyRecordRef, evidence.task_ref))
        if evidence.outcome_ref is not None:
            self.visit(cast(AnyRecordRef, evidence.outcome_ref))
        if evidence.evaluation_case_ref is not None:
            self.visit(cast(AnyRecordRef, evidence.evaluation_case_ref))

    def _visit_task(self, task: TaskRecord) -> None:
        self._add_partition(task.partition, relation="task")
        for reference in (
            *task.prompt_evidence_refs,
            *task.input_evidence_refs,
            *task.output_evidence_refs,
            *task.outcome_refs,
        ):
            self.visit(cast(AnyRecordRef, reference))

    def _visit_outcome(self, outcome: Outcome) -> None:
        self._add_partition(outcome.partition, relation="outcome")
        self.visit(cast(AnyRecordRef, outcome.task_ref))
        for reference in (
            *outcome.supporting_evidence_refs,
            *outcome.contradicting_evidence_refs,
        ):
            self.visit(cast(AnyRecordRef, reference))

    def _visit_case(self, case: EvaluationCase) -> None:
        self._add_partition(case.partition, relation="evaluation case")
        case_ref = cast(EvaluationCaseRef, record_ref(case))
        self._cases[record_ref_key(case_ref)] = case_ref
        if case.source_task_ref is not None:
            self.visit(cast(AnyRecordRef, case.source_task_ref))
        if case.source_outcome_ref is not None:
            self.visit(cast(AnyRecordRef, case.source_outcome_ref))
        for reference in (*case.source_evidence_refs, *case.setup.allowed_context_refs):
            self.visit(reference)

    def _visit_candidate(self, candidate: LessonCandidate) -> None:
        for reference in (
            *candidate.evidence_links.supporting,
            *candidate.evidence_links.contradicting,
            *candidate.evidence_links.scope_limiting,
            *candidate.source_task_refs,
            *candidate.source_outcome_refs,
            *candidate.evaluation_case_refs,
        ):
            self.visit(cast(AnyRecordRef, reference))
        for attestation in candidate.evaluation_attestations:
            self._add_partition(attestation.partition, relation="candidate attestation")
            self.visit(cast(AnyRecordRef, attestation.case_ref))


def build_release_render_projection(
    release: Release,
    records: Iterable[VersionedRecord],
    *,
    evaluated_at: datetime | None = None,
) -> ReleaseRenderProjection:
    """Resolve and gate an immutable release into the payload-free renderer projection."""

    release = _strict(release, Release, label="release")
    materialized = _strict_records(records)
    evaluation_time = evaluated_at or release.released_at
    if evaluation_time.tzinfo is None or evaluation_time.utcoffset() is None:
        raise TargetingError("release gate evaluation time must be timezone-aware")

    candidate = propose_release_candidate(
        candidate_id=release.record_id,
        candidate_version=release.release_version,
        created_at=release.created_at,
        created_by=release.created_by,
        policy_version=release.policy_version,
        artifact_refs=release.artifact_refs,
        schema_versions=release.schema_versions,
        policy_versions=release.policy_versions,
        construction_boundary=release.construction_boundary,
        development_evaluations=release.development_evaluations,
        predecessor_ref=release.predecessor_ref,
        supersedes_refs=release.supersedes_refs,
        rollback_target_ref=release.rollback_target_ref,
        target_compatibility=release.target_compatibility,
        proposal_disposition_id="projection-gate",
        proposal_rationale="Re-evaluate immutable release membership before rendering",
    )
    gate_report = evaluate_release_gates(
        candidate,
        materialized,
        evaluated_at=evaluation_time,
    )
    if not gate_report.passed:
        raise _decision_error(
            "release render gate failed",
            (
                f"{violation.code.value}: {violation.message}"
                for violation in gate_report.violations
            ),
        )
    membership = validate_release_membership(release, materialized)
    if not membership.allowed:
        raise _decision_error(
            "release membership validation failed",
            (violation.message for violation in membership.violations),
        )

    index = index_records(materialized)
    artifacts = tuple(
        _resolve_exact(index, reference, Artifact, relation="release artifact")
        for reference in release.artifact_refs
    )
    artifact_ids = tuple(artifact.record_id for artifact in artifacts)
    if len(artifact_ids) != len(set(artifact_ids)):
        raise TargetingError("release contains multiple versions of one conceptual artifact")

    release_attestations: dict[tuple[str, str], list[tuple[EvaluationCaseRef, Partition]]] = {}
    for attestation in release.development_evaluations:
        subject = _resolve_exact(
            index,
            attestation.subject_ref,
            Artifact,
            relation="release evaluation subject",
        )
        key = (subject.record_id, subject.record_version)
        release_attestations.setdefault(key, []).append(
            (attestation.case_ref, attestation.partition)
        )

    projections: list[ArtifactRenderProjection] = []
    for artifact in artifacts:
        sources = _ProjectionSources(index)
        sources.add_artifact(artifact)
        for case_ref, partition in release_attestations.get(
            (artifact.record_id, artifact.record_version), []
        ):
            sources.add_release_attestation(case_ref, partition)
        projections.append(
            ArtifactRenderProjection(
                artifact_ref=cast(ArtifactRef, record_ref(artifact)),
                artifact_type=artifact.artifact_kind,
                behavioral_contract=artifact.behavioral_contract,
                scope=artifact.scope,
                evidence_links=artifact.evidence_links,
                evaluation_cases=sources.evaluation_cases,
                claim_authorities=artifact.claim_authorities,
                privacy=artifact.privacy,
                precedence=artifact.priority,
                review_at=artifact.review_at,
                expires_at=artifact.expires_at,
                target_compatibility=artifact.target_compatibility,
                required=True,
                revoked=False,
                source_partitions=sources.partitions,
            )
        )
    return ReleaseRenderProjection(
        release_ref=cast(ReleaseRef, record_ref(release)),
        release_version=release.release_version,
        policy_version=release.policy_version,
        artifacts=tuple(projections),
        target_compatibility=release.target_compatibility,
        explicit_empty=release.is_empty_release,
    )


def _artifact_applies(artifact: Artifact, target: TargetKind) -> bool:
    if target in {TargetKind.GENERIC_JSON, TargetKind.GENERIC_MARKDOWN}:
        return True
    families = set(artifact.scope.target_families)
    return not families or target.value in families


def _scope_dimensions(artifact: Artifact) -> set[str]:
    scope = artifact.scope
    result = {ScopeDimension.SUBJECT_IDS.value}
    for field in (
        "workspace_ids",
        "project_ids",
        "repository_ids",
        "task_classes",
        "target_families",
        "environment_ids",
        "activation_conditions",
        "exclusions",
    ):
        if getattr(scope, field):
            result.add(field)
    if (
        scope.valid_from is not None
        or scope.valid_until is not None
        or artifact.review_at is not None
        or artifact.expires_at is not None
    ):
        result.add(ScopeDimension.VALIDITY_WINDOW.value)
    return result


def _expected_artifact_paths(artifact: Artifact, target: TargetKind) -> tuple[str, ...]:
    if target is TargetKind.GENERIC_JSON:
        return ("adaptation-pack.json",)
    if target is TargetKind.GENERIC_MARKDOWN:
        return ("ADAPTATION.md",)
    slug = safe_slug(artifact.record_id)
    if target is TargetKind.CODEX:
        if artifact.artifact_kind in {ArtifactKind.PROCEDURE, ArtifactKind.SKILL}:
            return (f".agents/skills/{slug}/SKILL.md",)
        return ("AGENTS.md",)
    if artifact.artifact_kind in {ArtifactKind.PROCEDURE, ArtifactKind.SKILL}:
        return (f".claude/skills/{slug}/SKILL.md",)
    return (f".claude/rules/{slug}.md",)


def _base_output_paths(target: TargetKind) -> set[str]:
    if target is TargetKind.GENERIC_JSON:
        return {"adaptation-pack.json"}
    if target is TargetKind.GENERIC_MARKDOWN:
        return {"ADAPTATION.md"}
    if target is TargetKind.CODEX:
        return {"AGENTS.md"}
    return {"CLAUDE.md"}


def _primary_paths(target: TargetKind, paths: Iterable[str]) -> tuple[str, ...]:
    if target is TargetKind.GENERIC_JSON:
        return ("adaptation-pack.json",)
    if target is TargetKind.GENERIC_MARKDOWN:
        return ("ADAPTATION.md",)
    if target is TargetKind.CODEX:
        return ("AGENTS.md",)
    return tuple(
        sorted(path for path in paths if path == "CLAUDE.md" or path.startswith(".claude/rules/"))
    )


def _validate_profile_artifact(
    artifact: Artifact,
    profile: FileTargetCapabilityProfile,
    *,
    build_time: datetime,
) -> None:
    capabilities = profile.capabilities
    if artifact.artifact_kind not in capabilities.supported_artifact_kinds:
        raise TargetingError(
            f"target profile cannot represent artifact kind {artifact.artifact_kind.value}"
        )
    unsupported = _scope_dimensions(artifact) - set(capabilities.supported_scope_dimensions)
    if unsupported:
        raise TargetingError(
            "target profile cannot preserve artifact scope dimensions: "
            + ", ".join(sorted(unsupported))
        )
    if artifact.priority and not capabilities.supports_precedence:
        raise TargetingError("target profile cannot preserve artifact precedence")
    if (artifact.review_at is not None or artifact.expires_at is not None) and not (
        capabilities.supports_expiry
    ):
        raise TargetingError("target profile cannot preserve review or expiry bounds")
    if artifact.expires_at is not None and artifact.expires_at <= build_time:
        raise TargetingError(f"expired artifact cannot enter target pack: {artifact.record_id}")
    if (
        _SENSITIVITY_RANK[artifact.privacy.sensitivity]
        > _SENSITIVITY_RANK[capabilities.maximum_sensitivity]
    ):
        raise TargetingError("artifact sensitivity exceeds target profile ceiling")
    if artifact.privacy.review_state is not PrivacyReviewState.APPROVED:
        raise TargetingError("artifact privacy review is not approved")
    if PermittedUse.TARGET_DELIVERY not in artifact.privacy.permitted_uses:
        raise TargetingError("artifact privacy scope does not permit target delivery")


def _expected_manifest(
    pack: RenderedPack,
    profile: FileTargetCapabilityProfile,
    release: Release,
    files: dict[str, str],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "renderer": {"id": pack.renderer_id, "version": pack.renderer_version},
        "target_profile": {
            "id": profile.capabilities.profile_id,
            "version": profile.capabilities.profile_version,
            "target": profile.target.value,
            "documentation_uri": profile.documentation_uri,
            "documentation_checked_on": profile.documentation_checked_on,
        },
        "release": {
            "id": release.record_id,
            "version": release.release_version,
            "digest": canonical_digest(release),
            "policy_version": release.policy_version,
            "target_compatibility": list(release.target_compatibility),
        },
        "files": [
            {"path": path, "content_digest": sha256_text(files[path])}
            for path in sorted(files)
            if path != MANIFEST_PATH
        ],
        "entries": [entry.model_dump(mode="json") for entry in pack.entries],
        "omissions": [omission.model_dump(mode="json") for omission in pack.omissions],
        "losses": [],
        "raw_evidence_included": False,
    }


def _validate_rendered_files(
    pack: RenderedPack,
    profile: FileTargetCapabilityProfile,
    release: Release,
) -> dict[str, str]:
    paths = tuple(item.path for item in pack.files)
    if paths != tuple(sorted(set(paths))):
        raise TargetingError("rendered file paths must be sorted and unique")
    files: dict[str, str] = {}
    total_bytes = 0
    for rendered_file in pack.files:
        if is_sensitive_path(rendered_file.path):
            raise TargetingError(f"rendered output uses a sensitive path: {rendered_file.path}")
        try:
            assert_export_safe(rendered_file.content, label=rendered_file.path)
        except ExportSafetyError as error:
            raise TargetingError(str(error)) from error
        actual_digest = sha256_text(rendered_file.content)
        if rendered_file.content_digest != actual_digest:
            raise TargetingError(f"rendered file digest mismatch: {rendered_file.path}")
        files[rendered_file.path] = rendered_file.content
        total_bytes += len(rendered_file.content.encode("utf-8"))
    if MANIFEST_PATH not in files:
        raise TargetingError("rendered pack is missing its canonical manifest")
    if total_bytes != pack.total_bytes:
        raise TargetingError("rendered pack total byte count is incorrect")
    if total_bytes > profile.max_total_bytes:
        raise TargetingError("rendered pack exceeds the target profile byte limit")
    actual_pack_digest = sha256_text(
        target_canonical_json(
            [{"path": item.path, "content_digest": item.content_digest} for item in pack.files]
        )
    )
    if pack.pack_digest != actual_pack_digest:
        raise TargetingError("rendered pack aggregate digest mismatch")

    manifest = _expected_manifest(pack, profile, release, files)
    expected_content = target_canonical_json(manifest)
    if files[MANIFEST_PATH] != expected_content:
        try:
            parsed = json.loads(files[MANIFEST_PATH])
        except json.JSONDecodeError as error:
            raise TargetingError("rendered pack manifest is not valid JSON") from error
        if not isinstance(parsed, dict):
            raise TargetingError("rendered pack manifest must be a JSON object")
        if parsed.get("raw_evidence_included") is not False:
            raise TargetingError("rendered pack manifest does not exclude raw evidence")
        if parsed.get("losses") != []:
            raise TargetingError("rendered pack declares an unreviewed rendering loss")
        raise TargetingError("rendered pack manifest is not the exact canonical manifest")
    return files


def _entry_id(artifact_ref: ArtifactRef, path: str) -> str:
    identity = (
        f"{artifact_ref.record_id}\0{artifact_ref.record_version}\0"
        f"{artifact_ref.content_digest}\0{path}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"entry-{digest}"


def _evidence_refs(artifact: Artifact) -> tuple[EvidenceRef, ...]:
    references = {
        *artifact.evidence_links.supporting,
        *artifact.evidence_links.contradicting,
        *artifact.evidence_links.scope_limiting,
    }
    return tuple(sorted(references, key=record_ref_key))


def build_validated_target_pack(
    rendered_pack: RenderedPack,
    profile: FileTargetCapabilityProfile,
    release: Release,
    artifacts: Iterable[Artifact],
    *,
    context: TargetPackBuildContext,
) -> TargetPack:
    """Convert trusted renderer output into a validated, payload-free domain manifest.

    The function accepts only promoted artifacts, not ``Evidence`` records or payloads.  It
    independently rechecks all self-reported digests and exact cross-policy membership before
    returning a ``VALIDATED`` target pack.
    """

    rendered_pack = _strict(rendered_pack, RenderedPack, label="rendered pack")
    profile = _strict(profile, FileTargetCapabilityProfile, label="target profile")
    release = _strict(release, Release, label="release")
    context = _strict(context, TargetPackBuildContext, label="target-pack build context")
    strict_artifacts = tuple(
        _strict(artifact, Artifact, label=f"artifact {artifact.record_id!r}")
        for artifact in artifacts
    )
    try:
        index_records(strict_artifacts)
    except ValueError as error:
        raise TargetingError(f"artifact set is ambiguous: {error}") from error

    membership = validate_release_membership(release, strict_artifacts)
    if not membership.allowed:
        raise _decision_error(
            "release membership validation failed",
            (violation.message for violation in membership.violations),
        )
    artifact_by_ref = {
        cast(ArtifactRef, record_ref(artifact)): artifact for artifact in strict_artifacts
    }
    if set(artifact_by_ref) != set(release.artifact_refs):
        raise TargetingError("explicit artifact set must exactly equal release membership")
    artifact_ids = tuple(artifact.record_id for artifact in strict_artifacts)
    if len(artifact_ids) != len(set(artifact_ids)):
        raise TargetingError("release contains multiple versions of one conceptual artifact")

    release_ref = cast(ReleaseRef, record_ref(release))
    if (
        rendered_pack.release_id != release.record_id
        or rendered_pack.release_version != release.release_version
        or rendered_pack.release_digest != release_ref.content_digest
    ):
        raise TargetingError("rendered pack does not identify the exact immutable release")
    if (
        rendered_pack.target_profile_id != profile.capabilities.profile_id
        or rendered_pack.target_profile_version != profile.capabilities.profile_version
    ):
        raise TargetingError("rendered pack does not identify the explicit target profile")
    if rendered_pack.renderer_id != _RENDERER_IDS[profile.target]:
        raise TargetingError("rendered pack renderer is not recognized for the target profile")
    if rendered_pack.renderer_version != RENDERER_VERSION:
        raise TargetingError("rendered pack renderer version is not supported")
    if context.policy_version != release.policy_version:
        raise TargetingError("target-pack policy version must equal the gated release policy")
    if not _REQUIRED_SURFACES[profile.target] <= profile.supported_surfaces:
        raise TargetingError("target profile omits a renderer-required output surface")
    if not profile.capabilities.supports_evidence_trace:
        raise TargetingError("target profile cannot preserve evidence traceability")
    if not profile.capabilities.supports_authority_labels:
        raise TargetingError("target profile cannot preserve claim-specific authority")
    known_dimensions = {dimension.value for dimension in ScopeDimension}
    if not set(profile.capabilities.supported_scope_dimensions) <= known_dimensions:
        raise TargetingError("target profile declares an unknown scope capability")

    compatible_profile_ids = {
        profile.capabilities.profile_id,
        profile.capabilities.target_family,
    }
    deployable = profile.target in {TargetKind.CODEX, TargetKind.CLAUDE_CODE}
    if (
        deployable
        and release.target_compatibility
        and not compatible_profile_ids & set(release.target_compatibility)
    ):
        raise TargetingError("release target compatibility excludes the explicit profile")

    included = tuple(
        sorted(
            (
                artifact
                for artifact in strict_artifacts
                if _artifact_applies(artifact, profile.target)
            ),
            key=lambda artifact: (
                artifact.priority,
                artifact.record_id,
                artifact.record_version,
            ),
        )
    )
    omitted = tuple(
        sorted(
            (
                artifact
                for artifact in strict_artifacts
                if not _artifact_applies(artifact, profile.target)
            ),
            key=lambda artifact: artifact.record_id,
        )
    )
    if len(included) > profile.max_entries:
        raise TargetingError("rendered pack exceeds the target profile entry limit")
    for artifact in included:
        _validate_profile_artifact(artifact, profile, build_time=context.created_at)
        if (
            deployable
            and artifact.target_compatibility
            and not compatible_profile_ids & set(artifact.target_compatibility)
        ):
            raise TargetingError(
                f"artifact target compatibility excludes the explicit profile: {artifact.record_id}"
            )

    expected_entry_ids = tuple(artifact.record_id for artifact in included)
    if tuple(entry.artifact_id for entry in rendered_pack.entries) != expected_entry_ids:
        raise TargetingError("rendered entries do not exactly match applicable release artifacts")
    expected_omissions = tuple(
        RenderOmission(
            artifact_id=artifact.record_id,
            reason="artifact target-family scope excludes this target",
        )
        for artifact in omitted
    )
    if rendered_pack.omissions != expected_omissions:
        raise TargetingError("rendered omissions are unresolved or represent material loss")
    if tuple(rendered_pack.warnings) != tuple(sorted(set(rendered_pack.warnings))):
        raise TargetingError("rendered warnings must be sorted and unique")

    artifact_by_id = {artifact.record_id: artifact for artifact in strict_artifacts}
    expected_paths = _base_output_paths(profile.target)
    component_paths: list[str] = []
    for artifact in included:
        artifact_paths = _expected_artifact_paths(artifact, profile.target)
        expected_paths.update(artifact_paths)
        component_paths.extend(
            path
            for path in artifact_paths
            if path not in {"AGENTS.md", "ADAPTATION.md", "adaptation-pack.json"}
        )
    if len(component_paths) != len(set(component_paths)):
        raise TargetingError("artifact identifiers collide on a target component path")
    expected_paths.add(MANIFEST_PATH)
    files = _validate_rendered_files(rendered_pack, profile, release)
    if set(files) != expected_paths:
        raise TargetingError("rendered pack contains missing or unrecognized target files")

    domain_entries: list[DomainRenderedEntry] = []
    for rendered_entry in rendered_pack.entries:
        resolved_artifact = artifact_by_id.get(rendered_entry.artifact_id)
        if resolved_artifact is None:
            raise TargetingError("rendered entry references an unresolved artifact")
        artifact = resolved_artifact
        artifact_ref = cast(ArtifactRef, record_ref(artifact))
        if (
            rendered_entry.artifact_version != artifact.record_version
            or rendered_entry.artifact_digest != artifact_ref.content_digest
        ):
            raise TargetingError("rendered entry artifact digest or version is not exact")
        if rendered_entry.paths != _expected_artifact_paths(artifact, profile.target):
            raise TargetingError("rendered entry paths do not match the recognized renderer layout")
        if rendered_entry.supporting_evidence_ids != tuple(
            reference.record_id for reference in artifact.evidence_links.supporting
        ):
            raise TargetingError("rendered entry changed its supporting-evidence trace")
        if rendered_entry.contradicting_evidence_ids != tuple(
            reference.record_id for reference in artifact.evidence_links.contradicting
        ):
            raise TargetingError("rendered entry changed its contradicting-evidence trace")
        if rendered_entry.scope_limiting_evidence_ids != tuple(
            reference.record_id for reference in artifact.evidence_links.scope_limiting
        ):
            raise TargetingError("rendered entry changed its scope-limiting-evidence trace")
        authority_digest = canonical_digest(artifact.claim_authorities)
        if rendered_entry.authority_digest != authority_digest:
            raise TargetingError("rendered entry changed claim-specific authority")
        for path in rendered_entry.paths:
            if path not in files or path == MANIFEST_PATH:
                raise TargetingError("rendered entry references a missing or reserved output file")
            content = files[path]
            domain_entries.append(
                DomainRenderedEntry(
                    entry_id=_entry_id(artifact_ref, path),
                    output_path=path,
                    content_digest=sha256_text(content),
                    byte_length=len(content.encode("utf-8")),
                    artifact_ref=artifact_ref,
                    evidence_refs=_evidence_refs(artifact),
                    precedence=artifact.priority,
                    scope_digest=canonical_digest(artifact.scope),
                    behavioral_contract_digest=canonical_digest(artifact.behavioral_contract),
                    authority_digest=authority_digest,
                )
            )

    primary_paths = _primary_paths(profile.target, files)
    primary_bytes = sum(len(files[path].encode("utf-8")) for path in primary_paths)
    if primary_bytes > profile.max_primary_instruction_bytes:
        raise TargetingError("rendered pack exceeds the primary-instruction byte limit")
    primary_lines = sum(files[path].count("\n") for path in primary_paths)
    if (
        profile.max_primary_instruction_lines is not None
        and primary_lines > profile.max_primary_instruction_lines
    ):
        raise TargetingError("rendered pack exceeds the primary-instruction line limit")

    if context.privacy.review_state is not PrivacyReviewState.APPROVED:
        raise TargetingError("target-pack privacy review is not approved")
    if PermittedUse.TARGET_DELIVERY not in context.privacy.permitted_uses:
        raise TargetingError("target-pack privacy scope does not permit target delivery")
    if context.privacy.sensitivity is SensitivityClass.PROHIBITED_SECRET:
        raise TargetingError("secret-classified content cannot enter a target pack")
    highest_artifact_sensitivity = max(
        (_SENSITIVITY_RANK[artifact.privacy.sensitivity] for artifact in included),
        default=0,
    )
    if _SENSITIVITY_RANK[context.privacy.sensitivity] < highest_artifact_sensitivity:
        raise TargetingError("target-pack privacy classification understates release content")
    if (
        _SENSITIVITY_RANK[context.privacy.sensitivity]
        > _SENSITIVITY_RANK[profile.capabilities.maximum_sensitivity]
    ):
        raise TargetingError("target-pack privacy classification exceeds target capability")

    omitted_refs = tuple(cast(ArtifactRef, record_ref(artifact)) for artifact in omitted)
    losses = tuple(
        RenderingLoss(
            field_path=f"artifacts.{artifact.record_id}.scope.target_families",
            materiality=LossMateriality.NON_MATERIAL,
            reason="artifact target-family scope excludes this target",
            artifact_ref=cast(ArtifactRef, record_ref(artifact)),
        )
        for artifact in omitted
    )
    pack = TargetPack(
        record_id=context.record_id,
        record_version=context.record_version,
        created_at=context.created_at,
        created_by=context.created_by,
        policy_version=context.policy_version,
        state=TargetPackState.VALIDATED,
        release_ref=release_ref,
        target_profile=profile.capabilities,
        renderer_version=rendered_pack.renderer_version,
        entries=tuple(sorted(domain_entries, key=lambda entry: entry.entry_id)),
        ordering_rationale=(
            "Artifact precedence is preserved on every deterministically identified entry.",
        ),
        omitted_artifact_refs=omitted_refs,
        losses=losses,
        warnings=rendered_pack.warnings,
        context_token_cost=context.context_token_cost,
        runtime_selector_digest=context.runtime_selector_digest,
        privacy=context.privacy,
        material_semantics_preserved=True,
    )
    policy = validate_target_pack(pack, (release, *strict_artifacts))
    if not policy.allowed:
        raise _decision_error(
            "target-pack cross-policy validation failed",
            (violation.message for violation in policy.violations),
        )
    return pack


# Concise aliases for callers that describe the operations rather than their return types.
project_release_for_rendering = build_release_render_projection
build_target_pack = build_validated_target_pack


__all__ = [
    "TargetPackBuildContext",
    "TargetingError",
    "build_release_render_projection",
    "build_target_pack",
    "build_validated_target_pack",
    "project_release_for_rendering",
]
