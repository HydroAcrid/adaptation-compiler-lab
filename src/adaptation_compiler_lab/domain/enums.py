"""Closed vocabularies for the version 1 domain contracts."""

from enum import StrEnum


class RecordKind(StrEnum):
    """Top-level records supported by the version 1 interchange contract."""

    TASK_RECORD = "task_record"
    OUTCOME = "outcome"
    EVIDENCE = "evidence"
    EVALUATION_CASE = "evaluation_case"
    LESSON_CANDIDATE = "lesson_candidate"
    ARTIFACT = "artifact"
    RELEASE = "release"
    TARGET_PACK = "target_pack"


class ActorKind(StrEnum):
    USER = "user"
    HUMAN_REVIEWER = "human_reviewer"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"


class SourceClass(StrEnum):
    EXPLICIT_USER_FEEDBACK = "explicit_user_feedback"
    AUTHORIZED_HUMAN_EVALUATION = "authorized_human_evaluation"
    DETERMINISTIC_EXECUTION_OBSERVATION = "deterministic_execution_observation"
    AGENT_GENERATED = "agent_generated"
    TOOL_OUTPUT = "tool_output"
    REPOSITORY_CONTENT = "repository_content"
    WEB_CONTENT = "web_content"
    RETRIEVED_DOCUMENT = "retrieved_document"
    SYSTEM_POLICY = "system_policy"
    SYNTHETIC = "synthetic"


class AuthorityClass(StrEnum):
    USER_NORMATIVE = "user_normative"
    AUTHORIZED_EVALUATOR = "authorized_evaluator"
    PROJECT_POLICY = "project_policy"
    OBSERVATIONAL = "observational"
    PROPOSAL_ONLY = "proposal_only"
    UNTRUSTED_CONTEXT = "untrusted_context"
    SYNTHETIC_ONLY = "synthetic_only"


class ClaimType(StrEnum):
    USER_PREFERENCE = "user_preference"
    USER_CORRECTION = "user_correction"
    USER_ACCEPTANCE = "user_acceptance"
    PROJECT_REQUIREMENT = "project_requirement"
    TASK_OUTCOME = "task_outcome"
    BEHAVIORAL_EFFECTIVENESS = "behavioral_effectiveness"
    REPOSITORY_FACT = "repository_fact"
    EXTERNAL_FACT = "external_fact"
    PROPOSED_LESSON = "proposed_lesson"
    SYNTHETIC_EXPECTATION = "synthetic_expectation"


class SensitivityClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PROHIBITED_SECRET = "prohibited_secret"


class PermittedUse(StrEnum):
    CONSTRUCTION = "construction"
    DEVELOPMENT_EVALUATION = "development_evaluation"
    PROMOTION = "promotion"
    TARGET_DELIVERY = "target_delivery"
    BENCHMARK = "benchmark"
    AUDIT = "audit"


class PrivacyReviewState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Partition(StrEnum):
    CONSTRUCTION = "construction"
    DEVELOPMENT = "development"
    HELD_OUT = "held_out"
    SYNTHETIC = "synthetic"


class EvidenceState(StrEnum):
    RAW = "raw"
    DERIVED = "derived"
    TOMBSTONED = "tombstoned"


class RedactionState(StrEnum):
    NONE = "none"
    REDACTED = "redacted"
    TOMBSTONED = "tombstoned"


class OutcomeKind(StrEnum):
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    REVERTED = "reverted"
    TEST_RESULT = "test_result"
    EXPLICIT_RATING = "explicit_rating"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CORRECTION = "correction"
    UNKNOWN = "unknown"


class AssertionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class ScoringType(StrEnum):
    OBJECTIVE = "objective"
    SUBJECTIVE = "subjective"
    HYBRID = "hybrid"


class EvaluationCaseState(StrEnum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class EvaluationCaseKind(StrEnum):
    PROMOTION = "promotion"
    REGRESSION = "regression"
    DEVELOPMENT = "development"
    BENCHMARK = "benchmark"


class LessonKind(StrEnum):
    STABLE_FACT = "stable_fact"
    EXPLICIT_PREFERENCE = "explicit_preference"
    SUCCESSFUL_EXAMPLE = "successful_example"
    REPEATABLE_WORKFLOW = "repeatable_workflow"
    GLOBAL_BEHAVIOR = "global_behavior"
    COORDINATED_INSTRUCTION_BUNDLE = "coordinated_instruction_bundle"
    MISSING_CAPABILITY = "missing_capability"
    ADAPTER_DATASET_PATTERN = "adapter_dataset_pattern"
    UNCERTAIN = "uncertain"


class LessonCandidateState(StrEnum):
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    PROMOTED = "promoted"


class ArtifactKind(StrEnum):
    MEMORY = "memory"
    PREFERENCE = "preference"
    EXAMPLE = "example"
    PROCEDURE = "procedure"
    PROMPT_RULE = "prompt_rule"
    SKILL = "skill"
    TOOL_RECOMMENDATION = "tool_recommendation"


class ArtifactRoute(StrEnum):
    EVALUATION_ONLY = "evaluation_only"
    MEMORY = "memory"
    PREFERENCE = "preference"
    EXAMPLE = "example"
    PROCEDURE = "procedure"
    PROMPT_RULE = "prompt_rule"
    SKILL = "skill"
    TOOL_RECOMMENDATION = "tool_recommendation"
    INACTIVE_TOOL_CANDIDATE = "inactive_tool_candidate"
    INACTIVE_ADAPTER_DATASET_CANDIDATE = "inactive_adapter_dataset_candidate"


class ArtifactState(StrEnum):
    DRAFT = "draft"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"
    REVOKED = "revoked"


class ReleaseManifestState(StrEnum):
    RELEASED = "released"


class ReleaseCandidateState(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FROZEN = "frozen"


class TargetPackState(StrEnum):
    BUILT = "built"
    VALIDATED = "validated"
    REJECTED = "rejected"


class ActivationState(StrEnum):
    INACTIVE = "inactive"
    CANARY = "canary"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    ROLLED_BACK = "rolled_back"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class EvaluationResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class ConflictResolution(StrEnum):
    NARROWED = "narrowed"
    SUPERSEDES = "supersedes"
    EXCLUDED = "excluded"
    PRECEDENCE = "precedence"
    UNRESOLVED = "unresolved"


class LossMateriality(StrEnum):
    NON_MATERIAL = "non_material"
    MATERIAL = "material"
