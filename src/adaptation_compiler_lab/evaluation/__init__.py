"""Evaluation candidate generation and evaluation-first policy."""

from adaptation_compiler_lab.evaluation.candidates import (
    CandidateGenerationContext,
    CandidateGenerationIssue,
    DeterministicEvaluationCandidateGenerator,
    EvaluationCandidateBatch,
    EvaluationCandidateGenerator,
    generate_evaluation_candidates,
    outcome_requires_evaluation,
)
from adaptation_compiler_lab.evaluation.policy import validate_evaluation_first

__all__ = [
    "CandidateGenerationContext",
    "CandidateGenerationIssue",
    "DeterministicEvaluationCandidateGenerator",
    "EvaluationCandidateBatch",
    "EvaluationCandidateGenerator",
    "generate_evaluation_candidates",
    "outcome_requires_evaluation",
    "validate_evaluation_first",
]
