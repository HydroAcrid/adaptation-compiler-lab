"""Deterministic evaluation-candidate generation from structured outcome assertions."""

import hashlib
from typing import Protocol

from adaptation_compiler_lab.domain.base import (
    ActorRef,
    FrozenModel,
    Identifier,
    SemVer,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import (
    AssertionStatus,
    EvaluationCaseKind,
    EvaluationCaseState,
    OutcomeKind,
    Partition,
)
from adaptation_compiler_lab.domain.records import EvaluationCase, Outcome
from adaptation_compiler_lab.domain.references import OutcomeRef
from adaptation_compiler_lab.domain.values import EvaluationSetup, refs_are_sorted_unique
from adaptation_compiler_lab.serialization import record_ref


class CandidateGenerationContext(FrozenModel):
    generator: ActorRef
    generator_version: SemVer
    policy_version: SemVer
    generated_at: UtcDateTime


class CandidateGenerationIssue(FrozenModel):
    code: Identifier
    message: str
    assertion_id: Identifier | None = None


class EvaluationCandidateBatch(FrozenModel):
    source_outcome_ref: OutcomeRef
    candidates: tuple[EvaluationCase, ...]
    issues: tuple[CandidateGenerationIssue, ...] = ()


class EvaluationCandidateGenerator(Protocol):
    """Replaceable extraction boundary; implementations may only return review candidates."""

    def generate(
        self, outcome: Outcome, context: CandidateGenerationContext
    ) -> EvaluationCandidateBatch:
        """Generate proposal-only evaluation cases without promotion side effects."""

        ...


class DeterministicEvaluationCandidateGenerator:
    """Default offline generator over explicit structured outcome assertions only."""

    def generate(
        self, outcome: Outcome, context: CandidateGenerationContext
    ) -> EvaluationCandidateBatch:
        return generate_evaluation_candidates(outcome, context)


_TRIGGERING_OUTCOMES = frozenset(
    {OutcomeKind.CORRECTION, OutcomeKind.FAILURE, OutcomeKind.REJECTED, OutcomeKind.REVERTED}
)
_TRIGGERING_ASSERTIONS = frozenset(
    {AssertionStatus.FAILED, AssertionStatus.CORRECTED, AssertionStatus.REJECTED}
)


def outcome_requires_evaluation(outcome: Outcome) -> bool:
    if outcome.kind in _TRIGGERING_OUTCOMES:
        return True
    return outcome.kind is OutcomeKind.TEST_RESULT and any(
        assertion.status is AssertionStatus.FAILED for assertion in outcome.assertions
    )


def _candidate_id(outcome: Outcome, assertion_id: str, context: CandidateGenerationContext) -> str:
    stable_input = "\x1f".join(
        (
            outcome.record_id,
            outcome.record_version,
            assertion_id,
            context.generator_version,
            context.policy_version,
        )
    ).encode("utf-8")
    return f"eval-{hashlib.sha256(stable_input).hexdigest()[:32]}"


def generate_evaluation_candidates(
    outcome: Outcome, context: CandidateGenerationContext
) -> EvaluationCandidateBatch:
    """Convert eligible structured failures into stable, proposal-only evaluation cases.

    The function copies explicit structured fields and never interprets raw evidence or free-form
    task content. Calling it twice with identical inputs produces identical records.
    """

    outcome_reference = record_ref(outcome)
    if not isinstance(outcome_reference, OutcomeRef):
        raise TypeError("outcome produced a non-outcome reference")
    if outcome.partition is Partition.HELD_OUT:
        return EvaluationCandidateBatch(
            source_outcome_ref=outcome_reference,
            candidates=(),
            issues=(
                CandidateGenerationIssue(
                    code="held-out-blocked",
                    message="held-out outcomes cannot generate construction evaluation candidates",
                ),
            ),
        )
    if not outcome_requires_evaluation(outcome):
        return EvaluationCandidateBatch(
            source_outcome_ref=outcome_reference,
            candidates=(),
            issues=(
                CandidateGenerationIssue(
                    code="not-triggering",
                    message="outcome does not require an evaluation-first candidate",
                ),
            ),
        )
    evidence_refs = tuple(
        sorted(
            set((*outcome.supporting_evidence_refs, *outcome.contradicting_evidence_refs)),
            key=lambda item: (
                item.record_id,
                item.record_version,
                item.content_digest,
            ),
        )
    )
    if not refs_are_sorted_unique(evidence_refs):
        raise ValueError("generated evidence references are not canonical")
    candidates: list[EvaluationCase] = []
    issues: list[CandidateGenerationIssue] = []
    for assertion in outcome.assertions:
        if assertion.status not in _TRIGGERING_ASSERTIONS:
            continue
        candidates.append(
            EvaluationCase(
                record_id=_candidate_id(outcome, assertion.assertion_id, context),
                record_version="1.0.0",
                created_at=context.generated_at,
                created_by=context.generator,
                policy_version=context.policy_version,
                state=EvaluationCaseState.CANDIDATE,
                kind=EvaluationCaseKind.REGRESSION,
                setup=EvaluationSetup(
                    instructions=assertion.evaluation_setup,
                    stimulus=assertion.evaluation_stimulus,
                    allowed_context_refs=(outcome.task_ref,),
                    allowed_tools=outcome.environment.tool_ids,
                ),
                expected_behaviors=(assertion.expected_behavior,),
                failure_criteria=assertion.failure_criteria,
                scoring_rule=assertion.scoring_rule,
                environment=outcome.environment,
                scope=assertion.scope,
                source_task_ref=outcome.task_ref,
                source_outcome_ref=outcome_reference,
                source_evidence_refs=evidence_refs,
                partition=(
                    Partition.SYNTHETIC
                    if outcome.partition is Partition.SYNTHETIC
                    else Partition.DEVELOPMENT
                ),
                privacy=outcome.privacy,
            )
        )
    if not candidates:
        issues.append(
            CandidateGenerationIssue(
                code="no-triggering-assertion",
                message="triggering outcome has no failed, corrected, or rejected assertion",
            )
        )
    return EvaluationCandidateBatch(
        source_outcome_ref=outcome_reference,
        candidates=tuple(candidates),
        issues=tuple(issues),
    )
