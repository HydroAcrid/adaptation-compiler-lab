"""Pure evaluation-first eligibility checks."""

from collections.abc import Iterable

from adaptation_compiler_lab.domain.base import VersionedRecord
from adaptation_compiler_lab.domain.enums import (
    EvaluationCaseState,
    EvaluationResult,
    LessonCandidateState,
    Partition,
    RecordKind,
)
from adaptation_compiler_lab.domain.records import EvaluationCase, LessonCandidate, Outcome
from adaptation_compiler_lab.evaluation.candidates import outcome_requires_evaluation
from adaptation_compiler_lab.provenance import (
    PolicyDecision,
    PolicyViolation,
    ViolationCode,
    index_records,
    resolve_reference,
)


def validate_evaluation_first(
    candidate: LessonCandidate,
    records: Iterable[VersionedRecord],
    *,
    require_passing_attestation: bool,
) -> PolicyDecision:
    """Validate that every triggering source outcome has a reviewed case before promotion."""

    index = index_records(records)
    violations: list[PolicyViolation] = []
    cases: list[EvaluationCase] = []
    for reference in candidate.evaluation_case_refs:
        case = resolve_reference(index, reference)
        if not isinstance(case, EvaluationCase):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.MISSING_REFERENCE,
                    message="candidate evaluation reference is missing or digest-mismatched",
                    record_ids=(candidate.record_id, reference.record_id),
                )
            )
            continue
        cases.append(case)
    passing: set[tuple[str, str]] = set()
    for attestation in candidate.evaluation_attestations:
        subject = attestation.subject_ref
        exact_subject = (
            subject.record_type is RecordKind.LESSON_CANDIDATE
            and subject.record_id == candidate.record_id
            and subject.record_version == candidate.record_version
        )
        independent = (
            attestation.independent_of_proposer
            and attestation.evaluator.actor_id != candidate.created_by.actor_id
        )
        if not exact_subject:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVALUATION_FAILED,
                    message="candidate evaluation attestation targets another record version",
                    record_ids=(candidate.record_id, subject.record_id),
                    field_path=("evaluation_attestations",),
                )
            )
        if attestation.independent_of_proposer and not independent:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVALUATION_FAILED,
                    message="candidate proposer cannot be its independent evaluator",
                    record_ids=(candidate.record_id,),
                    field_path=("evaluation_attestations",),
                )
            )
        if (
            exact_subject
            and independent
            and attestation.result is EvaluationResult.PASSED
            and attestation.partition is not Partition.HELD_OUT
        ):
            passing.add((attestation.case_ref.record_id, attestation.case_ref.record_version))
    for outcome_reference in candidate.source_outcome_refs:
        outcome = resolve_reference(index, outcome_reference)
        if not isinstance(outcome, Outcome):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.MISSING_REFERENCE,
                    message="candidate outcome reference is missing or digest-mismatched",
                    record_ids=(candidate.record_id, outcome_reference.record_id),
                )
            )
            continue
        if not outcome_requires_evaluation(outcome):
            continue
        matching = [
            case
            for case in cases
            if case.source_outcome_ref is not None
            and case.source_outcome_ref.record_id == outcome.record_id
            and case.source_outcome_ref.record_version == outcome.record_version
            and case.state in {EvaluationCaseState.REVIEWED, EvaluationCaseState.APPROVED}
            and case.partition is not Partition.HELD_OUT
        ]
        if not matching:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVALUATION_REQUIRED,
                    message="triggering outcome lacks a reviewed construction-side evaluation case",
                    record_ids=(candidate.record_id, outcome.record_id),
                )
            )
            continue
        if require_passing_attestation and not any(
            (case.record_id, case.record_version) in passing for case in matching
        ):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVALUATION_FAILED,
                    message="triggering outcome lacks an independent passing attestation",
                    record_ids=(candidate.record_id, outcome.record_id),
                )
            )
    if require_passing_attestation and candidate.state not in {
        LessonCandidateState.APPROVED,
        LessonCandidateState.PROMOTED,
    }:
        violations.append(
            PolicyViolation(
                code=ViolationCode.CANDIDATE_NOT_APPROVED,
                message="candidate is not approved for artifact construction",
                record_ids=(candidate.record_id,),
            )
        )
    ordered = tuple(
        sorted(
            violations,
            key=lambda item: (item.code.value, item.record_ids, item.message),
        )
    )
    return PolicyDecision(allowed=not ordered, violations=ordered)
