"""Pure release-candidate gates over exact immutable domain records."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from enum import StrEnum
from typing import cast

from pydantic import BaseModel, model_validator

from adaptation_compiler_lab.domain import (
    AnyRecordRef,
    Artifact,
    ArtifactState,
    ConflictResolution,
    EvaluationCase,
    EvaluationCaseState,
    EvaluationResult,
    ExactRecordRef,
    FrozenModel,
    Partition,
    PermittedUse,
    PrivacyReviewState,
    Release,
    SensitivityClass,
    VersionedRecord,
)
from adaptation_compiler_lab.provenance import (
    RecordIndex,
    ViolationCode,
    index_records,
    resolve_reference,
    validate_artifact_promotion,
)
from adaptation_compiler_lab.provenance.graph import record_key
from adaptation_compiler_lab.release.proposals import ReleaseCandidate
from adaptation_compiler_lab.sanitization import ExportSafetyError, assert_export_safe
from adaptation_compiler_lab.serialization import canonical_json


class ReleaseGateCode(StrEnum):
    MISSING_EXACT_ARTIFACT = "missing_exact_artifact"
    ARTIFACT_NOT_APPROVED = "artifact_not_approved"
    ARTIFACT_POLICY = "artifact_policy"
    EVIDENCE = "evidence"
    EVALUATION = "evaluation"
    PRIVACY = "privacy"
    SECRET = "secret"
    CONFLICT = "conflict"
    HELD_OUT = "held_out"
    ARTIFACT_EXPIRED = "artifact_expired"
    MISSING_RELEASE_REFERENCE = "missing_release_reference"
    CONSTRUCTION_BOUNDARY = "construction_boundary"


class ReleaseGateViolation(FrozenModel):
    code: ReleaseGateCode
    message: str
    record_ids: tuple[str, ...] = ()


class ReleaseGateReport(FrozenModel):
    candidate_id: str
    candidate_version: str
    evaluated_at: datetime
    passed: bool
    evaluated_artifact_ids: tuple[str, ...]
    violations: tuple[ReleaseGateViolation, ...] = ()

    @model_validator(mode="after")
    def result_matches_violations(self) -> ReleaseGateReport:
        if self.passed == bool(self.violations):
            raise ValueError("gate report passes exactly when it has no violations")
        return self


_EVIDENCE_VIOLATIONS = {
    ViolationCode.AUTHORITY_MISMATCH,
    ViolationCode.CLAIM_NOT_AUTHORIZED,
    ViolationCode.AUTHORITY_ESCALATION,
    ViolationCode.EVIDENCE_INCOMPLETE,
    ViolationCode.MISSING_REFERENCE,
    ViolationCode.PROHIBITED_SENSITIVITY,
    ViolationCode.PRIVACY_BROADENING,
    ViolationCode.USE_NOT_PERMITTED,
}
_EVALUATION_VIOLATIONS = {
    ViolationCode.EVALUATION_REQUIRED,
    ViolationCode.EVALUATION_FAILED,
    ViolationCode.CANDIDATE_NOT_APPROVED,
}


def _policy_gate(code: ViolationCode) -> ReleaseGateCode:
    if code in {ViolationCode.HELD_OUT_CONTAMINATION, ViolationCode.PARTITION_MISMATCH}:
        return ReleaseGateCode.HELD_OUT
    if code in {ViolationCode.PRIVACY_NOT_APPROVED, ViolationCode.PRIVACY_BROADENING}:
        return ReleaseGateCode.PRIVACY
    if code is ViolationCode.UNRESOLVED_CONFLICT:
        return ReleaseGateCode.CONFLICT
    if code in _EVIDENCE_VIOLATIONS:
        return ReleaseGateCode.EVIDENCE
    if code in _EVALUATION_VIOLATIONS:
        return ReleaseGateCode.EVALUATION
    if code is ViolationCode.ARTIFACT_NOT_APPROVED:
        return ReleaseGateCode.ARTIFACT_NOT_APPROVED
    return ReleaseGateCode.ARTIFACT_POLICY


def evaluate_release_gates(
    candidate: ReleaseCandidate,
    records: Iterable[VersionedRecord],
    *,
    evaluated_at: datetime,
) -> ReleaseGateReport:
    """Evaluate exact membership, provenance, privacy, conflict, and holdout gates."""

    materialized = tuple(records)
    index = index_records(materialized)
    violations: list[ReleaseGateViolation] = []
    artifacts: list[Artifact] = []

    if candidate.policy_version not in candidate.policy_versions:
        violations.append(
            ReleaseGateViolation(
                code=ReleaseGateCode.ARTIFACT_POLICY,
                message="release candidate policy manifest omits its governing policy version",
            )
        )
    artifact_ids = [reference.record_id for reference in candidate.artifact_refs]
    if len(artifact_ids) != len(set(artifact_ids)):
        violations.append(
            ReleaseGateViolation(
                code=ReleaseGateCode.ARTIFACT_POLICY,
                message="release candidate contains multiple versions of one artifact identity",
                record_ids=tuple(sorted(set(artifact_ids))),
            )
        )

    for reference in candidate.artifact_refs:
        resolved = resolve_reference(index, reference)
        if not isinstance(resolved, Artifact):
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.MISSING_EXACT_ARTIFACT,
                    message="release candidate artifact reference is missing or digest-mismatched",
                    record_ids=(reference.record_id,),
                )
            )
            continue
        artifact = resolved
        artifacts.append(artifact)
        schema_release_version = f"{artifact.schema_version}.0"
        if schema_release_version not in candidate.schema_versions:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.ARTIFACT_POLICY,
                    message="release schema manifest omits an exact member schema version",
                    record_ids=(artifact.record_id,),
                )
            )
        if artifact.policy_version not in candidate.policy_versions:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.ARTIFACT_POLICY,
                    message="release policy manifest omits an exact member policy version",
                    record_ids=(artifact.record_id,),
                )
            )
        if artifact.state is not ArtifactState.APPROVED:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.ARTIFACT_NOT_APPROVED,
                    message="release membership requires an exact approved artifact version",
                    record_ids=(artifact.record_id,),
                )
            )
        other_records = tuple(
            item for item in materialized if record_key(item) != record_key(artifact)
        )
        decision = validate_artifact_promotion(artifact, other_records)
        for policy_violation in decision.violations:
            violations.append(
                ReleaseGateViolation(
                    code=_policy_gate(policy_violation.code),
                    message=f"{policy_violation.code.value}: {policy_violation.message}",
                    record_ids=policy_violation.record_ids,
                )
            )
        if artifact.privacy.review_state is not PrivacyReviewState.APPROVED:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.PRIVACY,
                    message="artifact privacy review is not approved",
                    record_ids=(artifact.record_id,),
                )
            )
        required_uses = {PermittedUse.PROMOTION, PermittedUse.TARGET_DELIVERY}
        if not required_uses <= set(artifact.privacy.permitted_uses):
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.PRIVACY,
                    message="artifact is not permitted for promotion and target delivery",
                    record_ids=(artifact.record_id,),
                )
            )
        if artifact.privacy.sensitivity is SensitivityClass.PROHIBITED_SECRET:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.PRIVACY,
                    message="secret-bearing artifact cannot enter a release",
                    record_ids=(artifact.record_id,),
                )
            )
        try:
            assert_export_safe(canonical_json(artifact), label="artifact")
        except ExportSafetyError:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.SECRET,
                    message="artifact contains prohibited secret-like content",
                    record_ids=(artifact.record_id,),
                )
            )
        if artifact.expires_at is not None and artifact.expires_at <= evaluated_at:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.ARTIFACT_EXPIRED,
                    message="expired artifact cannot enter a release",
                    record_ids=(artifact.record_id,),
                )
            )
        if any(
            attestation.partition is Partition.HELD_OUT
            for attestation in artifact.evaluation_attestations
        ):
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.HELD_OUT,
                    message="held-out evaluation attestation cannot enter release construction",
                    record_ids=(artifact.record_id,),
                )
            )
        for conflict in artifact.conflicts:
            conflict_record = resolve_reference(index, conflict.artifact_ref)
            if not isinstance(conflict_record, Artifact):
                violations.append(
                    ReleaseGateViolation(
                        code=ReleaseGateCode.CONFLICT,
                        message="artifact conflict reference is missing or digest-mismatched",
                        record_ids=(artifact.record_id, conflict.artifact_ref.record_id),
                    )
                )
            if conflict.resolution is ConflictResolution.UNRESOLVED:
                violations.append(
                    ReleaseGateViolation(
                        code=ReleaseGateCode.CONFLICT,
                        message="release contains an unresolved artifact conflict",
                        record_ids=(artifact.record_id, conflict.artifact_ref.record_id),
                    )
                )

    covered_artifact_keys: set[tuple[object, str, str]] = set()
    if candidate.artifact_refs and not candidate.development_evaluations:
        violations.append(
            ReleaseGateViolation(
                code=ReleaseGateCode.EVALUATION,
                message="non-empty release candidate requires development evaluations",
            )
        )
    candidate_artifact_keys = {record_key(artifact) for artifact in artifacts}
    for attestation in candidate.development_evaluations:
        case = resolve_reference(index, attestation.case_ref)
        subject = resolve_reference(index, cast(AnyRecordRef, attestation.subject_ref))
        if not isinstance(case, EvaluationCase) or case.state not in {
            EvaluationCaseState.REVIEWED,
            EvaluationCaseState.APPROVED,
        }:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.EVALUATION,
                    message="development attestation case is missing, mismatched, or unreviewed",
                    record_ids=(attestation.case_ref.record_id,),
                )
            )
        elif case.partition is Partition.HELD_OUT:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.HELD_OUT,
                    message="held-out evaluation case cannot gate release construction",
                    record_ids=(case.record_id,),
                )
            )
        if not isinstance(subject, Artifact) or record_key(subject) not in candidate_artifact_keys:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.EVALUATION,
                    message="development attestation does not target exact release membership",
                    record_ids=(attestation.subject_ref.record_id,),
                )
            )
        else:
            covered_artifact_keys.add(record_key(subject))
        if (
            attestation.result is not EvaluationResult.PASSED
            or not attestation.independent_of_proposer
        ):
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.EVALUATION,
                    message="development attestation must be an independent pass",
                    record_ids=(attestation.case_ref.record_id,),
                )
            )
        if attestation.partition is Partition.HELD_OUT:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.HELD_OUT,
                    message="held-out result cannot enter a release candidate",
                    record_ids=(attestation.case_ref.record_id,),
                )
            )
    for missing_key in sorted(candidate_artifact_keys - covered_artifact_keys, key=str):
        violations.append(
            ReleaseGateViolation(
                code=ReleaseGateCode.EVALUATION,
                message="approved artifact lacks candidate-level development coverage",
                record_ids=(missing_key[1],),
            )
        )

    release_references = tuple(
        reference
        for reference in (
            candidate.predecessor_ref,
            candidate.rollback_target_ref,
            *candidate.supersedes_refs,
        )
        if reference is not None
    )
    for release_reference in release_references:
        if not isinstance(resolve_reference(index, release_reference), Release):
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.MISSING_RELEASE_REFERENCE,
                    message="candidate release-history reference is missing or digest-mismatched",
                    record_ids=(release_reference.record_id,),
                )
            )

    cutoff = candidate.construction_boundary.construction_cutoff
    construction_records = _reachable_construction_records(artifacts, index)
    for record in construction_records:
        if record.created_at > cutoff:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.CONSTRUCTION_BOUNDARY,
                    message=(
                        "release provenance contains a record created after the construction cutoff"
                    ),
                    record_ids=(record.record_id,),
                )
            )
        attestations = getattr(record, "evaluation_attestations", ())
        for attestation in attestations:
            if attestation.evaluated_at > cutoff:
                violations.append(
                    ReleaseGateViolation(
                        code=ReleaseGateCode.CONSTRUCTION_BOUNDARY,
                        message=(
                            "release provenance contains an evaluation after the "
                            "construction cutoff"
                        ),
                        record_ids=(record.record_id, attestation.case_ref.record_id),
                    )
                )
    for attestation in candidate.development_evaluations:
        if attestation.evaluated_at > cutoff:
            violations.append(
                ReleaseGateViolation(
                    code=ReleaseGateCode.CONSTRUCTION_BOUNDARY,
                    message="release development evaluation postdates the construction cutoff",
                    record_ids=(attestation.case_ref.record_id,),
                )
            )

    ordered = tuple(
        sorted(
            set(violations),
            key=lambda item: (item.code.value, item.record_ids, item.message),
        )
    )
    return ReleaseGateReport(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        evaluated_at=evaluated_at,
        passed=not ordered,
        evaluated_artifact_ids=tuple(sorted(artifact.record_id for artifact in artifacts)),
        violations=ordered,
    )


def _reachable_construction_records(
    roots: Iterable[VersionedRecord],
    index: RecordIndex,
) -> tuple[VersionedRecord, ...]:
    """Resolve the exact transitive provenance reachable from release artifacts."""

    pending = list(roots)
    seen: dict[tuple[object, str, str], VersionedRecord] = {}
    while pending:
        record = pending.pop()
        key = (record.record_type, record.record_id, record.record_version)
        if key in seen:
            continue
        seen[key] = record
        for reference in _walk_exact_refs(record):
            resolved = resolve_reference(index, reference)
            if resolved is not None:
                pending.append(resolved)
    return tuple(seen[key] for key in sorted(seen, key=str))


def _walk_exact_refs(value: object) -> Iterator[AnyRecordRef]:
    if isinstance(value, ExactRecordRef):
        yield cast(AnyRecordRef, value)
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _walk_exact_refs(getattr(value, name))
        return
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield from _walk_exact_refs(value[key])
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_exact_refs(item)
