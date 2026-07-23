"""Exact, integrity-protected references between versioned records."""

from typing import Literal

from adaptation_compiler_lab.domain.base import FrozenModel, Identifier, SemVer, Sha256Digest
from adaptation_compiler_lab.domain.enums import RecordKind


class GovernanceRef(FrozenModel):
    """Exact content-addressed reference to one signed governance object."""

    governance_type: Literal[
        "consent_receipt",
        "capture_receipt",
        "dependency_impact",
        "invalidation_event",
        "tombstone_receipt",
        "recall_report",
        "custody_manifest",
        "benchmark_registration",
        "condition_material_receipt",
        "trial_result",
        "adjudication_record",
        "custody_access_event",
    ]
    object_id: Identifier
    schema_version: Literal["1.0"] = "1.0"
    content_digest: Sha256Digest


class ConsentReceiptRef(GovernanceRef):
    governance_type: Literal["consent_receipt"] = "consent_receipt"


class CaptureReceiptRef(GovernanceRef):
    governance_type: Literal["capture_receipt"] = "capture_receipt"


class DependencyImpactRef(GovernanceRef):
    governance_type: Literal["dependency_impact"] = "dependency_impact"


class InvalidationEventRef(GovernanceRef):
    governance_type: Literal["invalidation_event"] = "invalidation_event"


class TombstoneReceiptRef(GovernanceRef):
    governance_type: Literal["tombstone_receipt"] = "tombstone_receipt"


class RecallReportRef(GovernanceRef):
    governance_type: Literal["recall_report"] = "recall_report"


class CustodyManifestRef(GovernanceRef):
    governance_type: Literal["custody_manifest"] = "custody_manifest"


class BenchmarkRegistrationRef(GovernanceRef):
    governance_type: Literal["benchmark_registration"] = "benchmark_registration"


class ConditionMaterialReceiptRef(GovernanceRef):
    governance_type: Literal["condition_material_receipt"] = "condition_material_receipt"


class TrialResultRef(GovernanceRef):
    governance_type: Literal["trial_result"] = "trial_result"


class AdjudicationRecordRef(GovernanceRef):
    governance_type: Literal["adjudication_record"] = "adjudication_record"


class CustodyAccessEventRef(GovernanceRef):
    governance_type: Literal["custody_access_event"] = "custody_access_event"


class ExactRecordRef(FrozenModel):
    record_type: RecordKind
    record_id: Identifier
    record_version: SemVer
    content_digest: Sha256Digest | None = None


class TaskRecordRef(ExactRecordRef):
    record_type: Literal[RecordKind.TASK_RECORD] = RecordKind.TASK_RECORD
    # Task/Evidence are mutually associated. Exact task versioning avoids a cyclic hash while all
    # downstream, one-way derivation references remain content addressed.
    content_digest: Literal[None] = None


class OutcomeRef(ExactRecordRef):
    record_type: Literal[RecordKind.OUTCOME] = RecordKind.OUTCOME
    content_digest: Sha256Digest


class EvidenceRef(ExactRecordRef):
    record_type: Literal[RecordKind.EVIDENCE] = RecordKind.EVIDENCE
    content_digest: Sha256Digest


class EvaluationCaseRef(ExactRecordRef):
    record_type: Literal[RecordKind.EVALUATION_CASE] = RecordKind.EVALUATION_CASE
    content_digest: Sha256Digest


class LessonCandidateRef(ExactRecordRef):
    record_type: Literal[RecordKind.LESSON_CANDIDATE] = RecordKind.LESSON_CANDIDATE
    content_digest: Sha256Digest


class ArtifactRef(ExactRecordRef):
    record_type: Literal[RecordKind.ARTIFACT] = RecordKind.ARTIFACT
    content_digest: Sha256Digest


class ReleaseRef(ExactRecordRef):
    record_type: Literal[RecordKind.RELEASE] = RecordKind.RELEASE
    content_digest: Sha256Digest


class TargetPackRef(ExactRecordRef):
    record_type: Literal[RecordKind.TARGET_PACK] = RecordKind.TARGET_PACK
    content_digest: Sha256Digest


AnyRecordRef = (
    TaskRecordRef
    | OutcomeRef
    | EvidenceRef
    | EvaluationCaseRef
    | LessonCandidateRef
    | ArtifactRef
    | ReleaseRef
    | TargetPackRef
)
