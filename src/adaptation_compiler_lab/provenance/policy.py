"""Pure trust, provenance, promotion, release, and pack policy checks."""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import model_validator

from adaptation_compiler_lab.domain.base import FrozenModel, NonEmptyStr, VersionedRecord
from adaptation_compiler_lab.domain.enums import (
    ApprovalDecision,
    ArtifactState,
    AuthorityClass,
    ClaimType,
    ConflictResolution,
    EvaluationCaseState,
    EvaluationResult,
    LessonCandidateState,
    LossMateriality,
    OutcomeKind,
    Partition,
    PermittedUse,
    PrivacyReviewState,
    SensitivityClass,
    SourceClass,
    TargetPackState,
)
from adaptation_compiler_lab.domain.records import (
    Artifact,
    EvaluationCase,
    Evidence,
    LessonCandidate,
    Outcome,
    Release,
    TargetPack,
    TaskRecord,
)
from adaptation_compiler_lab.domain.references import AnyRecordRef
from adaptation_compiler_lab.domain.values import (
    EvidenceLinks,
    PrivacyContext,
    Scope,
    scope_is_within,
)
from adaptation_compiler_lab.provenance.graph import (
    RecordIndex,
    evidence_cycle,
    index_records,
    record_key,
    resolve_reference,
)
from adaptation_compiler_lab.routing import route_lesson
from adaptation_compiler_lab.serialization import canonical_digest


class ViolationCode(StrEnum):
    MISSING_REFERENCE = "missing_reference"
    AUTHORITY_MISMATCH = "authority_mismatch"
    CLAIM_NOT_AUTHORIZED = "claim_not_authorized"
    AUTHORITY_ESCALATION = "authority_escalation"
    HELD_OUT_CONTAMINATION = "held_out_contamination"
    PRIVACY_NOT_APPROVED = "privacy_not_approved"
    USE_NOT_PERMITTED = "use_not_permitted"
    PROHIBITED_SENSITIVITY = "prohibited_sensitivity"
    LINEAGE_CYCLE = "lineage_cycle"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    EVALUATION_REQUIRED = "evaluation_required"
    EVALUATION_FAILED = "evaluation_failed"
    SCOPE_BROADENING = "scope_broadening"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    CANDIDATE_NOT_APPROVED = "candidate_not_approved"
    ARTIFACT_NOT_APPROVED = "artifact_not_approved"
    RELEASE_MEMBERSHIP_MISMATCH = "release_membership_mismatch"
    TARGET_CAPABILITY_MISMATCH = "target_capability_mismatch"
    TARGET_TRACE_INCOMPLETE = "target_trace_incomplete"
    MATERIAL_RENDERING_LOSS = "material_rendering_loss"
    PARTITION_MISMATCH = "partition_mismatch"
    PRIVACY_BROADENING = "privacy_broadening"
    ROUTING_MISMATCH = "routing_mismatch"


class PolicyViolation(FrozenModel):
    code: ViolationCode
    message: NonEmptyStr
    record_ids: tuple[str, ...] = ()
    field_path: tuple[str, ...] = ()


class PolicyDecision(FrozenModel):
    allowed: bool
    violations: tuple[PolicyViolation, ...] = ()
    notes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def allowed_matches_violations(self) -> "PolicyDecision":
        if self.allowed == bool(self.violations):
            raise ValueError("allowed must be true exactly when violations are empty")
        return self


def _decision(
    violations: Iterable[PolicyViolation], *, notes: tuple[str, ...] = ()
) -> PolicyDecision:
    ordered = tuple(
        sorted(
            violations,
            key=lambda item: (item.code.value, item.record_ids, item.field_path, item.message),
        )
    )
    return PolicyDecision(allowed=not ordered, violations=ordered, notes=notes)


_SOURCE_AUTHORITY: dict[SourceClass, AuthorityClass] = {
    SourceClass.EXPLICIT_USER_FEEDBACK: AuthorityClass.USER_NORMATIVE,
    SourceClass.AUTHORIZED_HUMAN_EVALUATION: AuthorityClass.AUTHORIZED_EVALUATOR,
    SourceClass.DETERMINISTIC_EXECUTION_OBSERVATION: AuthorityClass.OBSERVATIONAL,
    SourceClass.AGENT_GENERATED: AuthorityClass.PROPOSAL_ONLY,
    SourceClass.TOOL_OUTPUT: AuthorityClass.UNTRUSTED_CONTEXT,
    SourceClass.REPOSITORY_CONTENT: AuthorityClass.UNTRUSTED_CONTEXT,
    SourceClass.WEB_CONTENT: AuthorityClass.UNTRUSTED_CONTEXT,
    SourceClass.RETRIEVED_DOCUMENT: AuthorityClass.UNTRUSTED_CONTEXT,
    SourceClass.SYSTEM_POLICY: AuthorityClass.PROJECT_POLICY,
    SourceClass.SYNTHETIC: AuthorityClass.SYNTHETIC_ONLY,
}


_SOURCE_CLAIMS: dict[SourceClass, frozenset[ClaimType]] = {
    SourceClass.EXPLICIT_USER_FEEDBACK: frozenset(
        {
            ClaimType.USER_PREFERENCE,
            ClaimType.USER_CORRECTION,
            ClaimType.USER_ACCEPTANCE,
            ClaimType.PROJECT_REQUIREMENT,
            ClaimType.TASK_OUTCOME,
        }
    ),
    SourceClass.AUTHORIZED_HUMAN_EVALUATION: frozenset(
        {ClaimType.TASK_OUTCOME, ClaimType.BEHAVIORAL_EFFECTIVENESS}
    ),
    SourceClass.DETERMINISTIC_EXECUTION_OBSERVATION: frozenset(
        {
            ClaimType.TASK_OUTCOME,
            ClaimType.BEHAVIORAL_EFFECTIVENESS,
            ClaimType.REPOSITORY_FACT,
        }
    ),
    SourceClass.AGENT_GENERATED: frozenset({ClaimType.PROPOSED_LESSON}),
    SourceClass.TOOL_OUTPUT: frozenset({ClaimType.TASK_OUTCOME, ClaimType.REPOSITORY_FACT}),
    SourceClass.REPOSITORY_CONTENT: frozenset({ClaimType.REPOSITORY_FACT}),
    SourceClass.WEB_CONTENT: frozenset({ClaimType.EXTERNAL_FACT}),
    SourceClass.RETRIEVED_DOCUMENT: frozenset({ClaimType.EXTERNAL_FACT, ClaimType.REPOSITORY_FACT}),
    SourceClass.SYSTEM_POLICY: frozenset({ClaimType.PROJECT_REQUIREMENT}),
    SourceClass.SYNTHETIC: frozenset(
        {ClaimType.SYNTHETIC_EXPECTATION, ClaimType.BEHAVIORAL_EFFECTIVENESS}
    ),
}


_NORMATIVE_CLAIMS = frozenset(
    {
        ClaimType.USER_PREFERENCE,
        ClaimType.USER_CORRECTION,
        ClaimType.USER_ACCEPTANCE,
        ClaimType.PROJECT_REQUIREMENT,
    }
)


def validate_evidence_authority(evidence: Evidence, index: RecordIndex) -> PolicyDecision:
    """Enforce claim-specific, non-transitive authority for one evidence record."""

    violations: list[PolicyViolation] = []
    expected_authority = _SOURCE_AUTHORITY[evidence.source_class]
    if evidence.authority_class is not expected_authority:
        violations.append(
            PolicyViolation(
                code=ViolationCode.AUTHORITY_MISMATCH,
                message=(
                    f"{evidence.source_class.value} requires {expected_authority.value} authority"
                ),
                record_ids=(evidence.record_id,),
                field_path=("authority_class",),
            )
        )
    unsupported = set(evidence.allowed_claim_types) - _SOURCE_CLAIMS[evidence.source_class]
    for claim in sorted(unsupported, key=lambda item: item.value):
        violations.append(
            PolicyViolation(
                code=ViolationCode.CLAIM_NOT_AUTHORIZED,
                message=f"source class cannot support {claim.value}",
                record_ids=(evidence.record_id,),
                field_path=("allowed_claim_types",),
            )
        )
    if evidence.parent_evidence_refs:
        parent_claims_by_authority: dict[AuthorityClass, set[ClaimType]] = {}
        parent_authorities: set[AuthorityClass] = set()
        for reference in evidence.parent_evidence_refs:
            parent = resolve_reference(index, reference)
            if not isinstance(parent, Evidence):
                violations.append(_missing_reference(reference, evidence.record_id))
                continue
            parent_authorities.add(parent.authority_class)
            parent_claims_by_authority.setdefault(parent.authority_class, set()).update(
                parent.allowed_claim_types
            )
            if not scope_is_within(evidence.scope, parent.scope):
                violations.append(
                    PolicyViolation(
                        code=ViolationCode.SCOPE_BROADENING,
                        message="derived evidence scope is broader than its parent",
                        record_ids=(evidence.record_id, parent.record_id),
                    )
                )
            if evidence.partition is not parent.partition:
                code = (
                    ViolationCode.HELD_OUT_CONTAMINATION
                    if parent.partition is Partition.HELD_OUT
                    else ViolationCode.PARTITION_MISMATCH
                )
                violations.append(
                    PolicyViolation(
                        code=code,
                        message="derived evidence must preserve its parent partition",
                        record_ids=(evidence.record_id, parent.record_id),
                    )
                )
            violations.extend(
                _privacy_monotonicity_violations(
                    owner_id=evidence.record_id,
                    child=evidence.privacy,
                    parent_id=parent.record_id,
                    parent=parent.privacy,
                )
            )
        downgraded_authorities = {
            AuthorityClass.PROPOSAL_ONLY,
            AuthorityClass.UNTRUSTED_CONTEXT,
        }
        if (
            evidence.authority_class not in parent_authorities
            and evidence.authority_class not in downgraded_authorities
        ):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.AUTHORITY_ESCALATION,
                    message="derived evidence elevated authority beyond every direct parent",
                    record_ids=(evidence.record_id,),
                    field_path=("authority_class",),
                )
            )
        escalated = set(evidence.allowed_claim_types) - parent_claims_by_authority.get(
            evidence.authority_class, set()
        )
        for claim in sorted(escalated, key=lambda item: item.value):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.AUTHORITY_ESCALATION,
                    message=f"derivation introduced unsupported authority for {claim.value}",
                    record_ids=(evidence.record_id,),
                    field_path=("allowed_claim_types",),
                )
            )
    return _decision(violations)


def _missing_reference(reference: AnyRecordRef, owner_id: str) -> PolicyViolation:
    return PolicyViolation(
        code=ViolationCode.MISSING_REFERENCE,
        message=(
            f"exact reference {reference.record_type.value}:{reference.record_id}:"
            f"{reference.record_version} is missing or digest-mismatched"
        ),
        record_ids=(owner_id, reference.record_id),
    )


def _privacy_monotonicity_violations(
    *,
    owner_id: str,
    child: PrivacyContext,
    parent_id: str,
    parent: PrivacyContext,
) -> tuple[PolicyViolation, ...]:
    """Prevent a derivative from lowering sensitivity or widening permitted uses."""

    violations: list[PolicyViolation] = []
    if _SENSITIVITY_RANK[child.sensitivity] < _SENSITIVITY_RANK[parent.sensitivity]:
        violations.append(
            PolicyViolation(
                code=ViolationCode.PRIVACY_BROADENING,
                message="derived record understates the sensitivity of its source",
                record_ids=(owner_id, parent_id),
                field_path=("privacy", "sensitivity"),
            )
        )
    widened_uses = set(child.permitted_uses) - set(parent.permitted_uses)
    if widened_uses:
        violations.append(
            PolicyViolation(
                code=ViolationCode.PRIVACY_BROADENING,
                message=(
                    "derived record adds uses not permitted by its source: "
                    + ", ".join(sorted(item.value for item in widened_uses))
                ),
                record_ids=(owner_id, parent_id),
                field_path=("privacy", "permitted_uses"),
            )
        )
    if child.consent_basis != parent.consent_basis:
        violations.append(
            PolicyViolation(
                code=ViolationCode.PRIVACY_BROADENING,
                message="derived record changed the source consent basis",
                record_ids=(owner_id, parent_id),
                field_path=("privacy", "consent_basis"),
            )
        )
    return tuple(violations)


def validate_lineage(records: Iterable[VersionedRecord]) -> PolicyDecision:
    materialized = tuple(records)
    index = index_records(materialized)
    violations: list[PolicyViolation] = []
    evidence = tuple(item for item in materialized if isinstance(item, Evidence))
    cycle = evidence_cycle(evidence)
    if cycle is not None:
        violations.append(
            PolicyViolation(
                code=ViolationCode.LINEAGE_CYCLE,
                message="evidence derivation graph contains a cycle",
                record_ids=cycle,
            )
        )
    for item in evidence:
        violations.extend(validate_evidence_authority(item, index).violations)
    return _decision(violations)


def validate_evidence_links(
    links: EvidenceLinks,
    index: RecordIndex,
    *,
    owner_id: str,
    required_use: PermittedUse,
) -> PolicyDecision:
    violations: list[PolicyViolation] = []
    all_refs = (*links.supporting, *links.contradicting, *links.scope_limiting)
    for reference in all_refs:
        evidence = resolve_reference(index, reference)
        if not isinstance(evidence, Evidence):
            violations.append(_missing_reference(reference, owner_id))
            continue
        violations.extend(validate_evidence_authority(evidence, index).violations)
        if evidence.partition is Partition.HELD_OUT:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.HELD_OUT_CONTAMINATION,
                    message="held-out evidence cannot influence construction or promotion",
                    record_ids=(owner_id, evidence.record_id),
                )
            )
        if required_use not in evidence.privacy.permitted_uses:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.USE_NOT_PERMITTED,
                    message=f"evidence is not permitted for {required_use.value}",
                    record_ids=(owner_id, evidence.record_id),
                )
            )
        if evidence.privacy.sensitivity is SensitivityClass.PROHIBITED_SECRET:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.PROHIBITED_SENSITIVITY,
                    message="secret-bearing evidence cannot support promotion",
                    record_ids=(owner_id, evidence.record_id),
                )
            )
        if evidence.state.value == "tombstoned":
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVIDENCE_INCOMPLETE,
                    message="tombstoned evidence requires dependent revalidation",
                    record_ids=(owner_id, evidence.record_id),
                )
            )
    return _decision(violations)


def _records_with_root(
    root: VersionedRecord, records: Iterable[VersionedRecord]
) -> tuple[VersionedRecord, ...]:
    """Return a graph containing exactly the caller-supplied root at its exact key."""

    root_key = record_key(root)
    return (*tuple(item for item in records if record_key(item) != root_key), root)


def validate_lesson_candidate(
    candidate: LessonCandidate,
    records: Iterable[VersionedRecord],
    *,
    required_use: PermittedUse,
    require_approved: bool,
) -> PolicyDecision:
    """Validate a candidate against every exact construction source it cites.

    This is intentionally independent of the write workflow so direct persistence cannot
    bypass scope, privacy, authority, or held-out isolation at release time.
    """

    materialized = _records_with_root(candidate, records)
    index = index_records(materialized)
    violations: list[PolicyViolation] = list(validate_lineage(materialized).violations)
    violations.extend(
        validate_evidence_links(
            candidate.evidence_links,
            index,
            owner_id=candidate.record_id,
            required_use=required_use,
        ).violations
    )

    linked_evidence = {
        *candidate.evidence_links.supporting,
        *candidate.evidence_links.contradicting,
        *candidate.evidence_links.scope_limiting,
    }
    for confidence_ref in candidate.confidence.basis_evidence_refs:
        if confidence_ref not in linked_evidence:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVIDENCE_INCOMPLETE,
                    message="confidence basis is not retained in the candidate evidence links",
                    record_ids=(candidate.record_id, confidence_ref.record_id),
                    field_path=("confidence", "basis_evidence_refs"),
                )
            )

    source_refs: tuple[AnyRecordRef, ...] = (
        *candidate.source_task_refs,
        *candidate.source_outcome_refs,
        *candidate.evaluation_case_refs,
        *tuple(linked_evidence),
        *candidate.confidence.basis_evidence_refs,
    )
    seen: set[tuple[object, str, str]] = set()
    for reference in source_refs:
        reference_identity = (
            reference.record_type,
            reference.record_id,
            reference.record_version,
        )
        if reference_identity in seen:
            continue
        seen.add(reference_identity)
        source = resolve_reference(index, reference)
        if not isinstance(source, (TaskRecord, Outcome, EvaluationCase, Evidence)):
            violations.append(_missing_reference(reference, candidate.record_id))
            continue
        if source.partition is Partition.HELD_OUT:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.HELD_OUT_CONTAMINATION,
                    message="held-out source cannot influence a lesson candidate",
                    record_ids=(candidate.record_id, source.record_id),
                )
            )
        if not scope_is_within(candidate.scope, source.scope):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.SCOPE_BROADENING,
                    message="lesson candidate scope is broader than a cited source",
                    record_ids=(candidate.record_id, source.record_id),
                    field_path=("scope",),
                )
            )
        if isinstance(source, Outcome):
            for assertion in source.assertions:
                if not scope_is_within(candidate.scope, assertion.scope):
                    violations.append(
                        PolicyViolation(
                            code=ViolationCode.SCOPE_BROADENING,
                            message=(
                                "lesson candidate scope is broader than a cited outcome assertion"
                            ),
                            record_ids=(candidate.record_id, source.record_id),
                            field_path=("scope", assertion.assertion_id),
                        )
                    )
        violations.extend(
            _privacy_monotonicity_violations(
                owner_id=candidate.record_id,
                child=candidate.privacy,
                parent_id=source.record_id,
                parent=source.privacy,
            )
        )

    for claim_authority in candidate.claim_authorities.entries:
        authorized = any(
            isinstance((evidence := resolve_reference(index, reference)), Evidence)
            and claim_authority.claim_type in evidence.allowed_claim_types
            and claim_authority.authority_class is evidence.authority_class
            for reference in claim_authority.evidence_refs
        )
        if not authorized:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.AUTHORITY_ESCALATION,
                    message=(
                        "lesson claim authority is not directly supported at the declared level"
                    ),
                    record_ids=(candidate.record_id,),
                    field_path=("claim_authorities", claim_authority.claim_type.value),
                )
            )

    if require_approved:
        if candidate.state not in {
            LessonCandidateState.APPROVED,
            LessonCandidateState.PROMOTED,
        }:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.CANDIDATE_NOT_APPROVED,
                    message="lesson candidate is not approved",
                    record_ids=(candidate.record_id,),
                )
            )
        if (
            candidate.approval is None
            or candidate.approval.decision is not ApprovalDecision.APPROVED
            or candidate.approval.policy_version != candidate.policy_version
            or candidate.approval.decided_at != candidate.created_at
        ):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.CANDIDATE_NOT_APPROVED,
                    message="lesson approval is absent, stale, or not bound to this policy version",
                    record_ids=(candidate.record_id,),
                    field_path=("approval",),
                )
            )
        for case_ref in candidate.evaluation_case_refs:
            case = resolve_reference(index, case_ref)
            if not isinstance(case, EvaluationCase) or case.state not in {
                EvaluationCaseState.REVIEWED,
                EvaluationCaseState.APPROVED,
            }:
                violations.append(
                    PolicyViolation(
                        code=ViolationCode.EVALUATION_REQUIRED,
                        message="approved lesson requires exact reviewed evaluation cases",
                        record_ids=(candidate.record_id, case_ref.record_id),
                    )
                )
    return _decision(violations)


_EVALUATION_FIRST_OUTCOMES = frozenset(
    {OutcomeKind.CORRECTION, OutcomeKind.FAILURE, OutcomeKind.REJECTED, OutcomeKind.REVERTED}
)


def validate_artifact_promotion(
    artifact: Artifact, records: Iterable[VersionedRecord]
) -> PolicyDecision:
    """Check cross-record promotion invariants without mutating any record."""

    materialized = _records_with_root(artifact, records)
    index = index_records(materialized)
    violations: list[PolicyViolation] = list(validate_lineage(materialized).violations)
    violations.extend(
        validate_evidence_links(
            artifact.evidence_links,
            index,
            owner_id=artifact.record_id,
            required_use=PermittedUse.PROMOTION,
        ).violations
    )
    if artifact.state is not ArtifactState.APPROVED:
        violations.append(
            PolicyViolation(
                code=ViolationCode.ARTIFACT_NOT_APPROVED,
                message="only approved artifact versions are promotion eligible",
                record_ids=(artifact.record_id,),
            )
        )
    if (
        artifact.approval is None
        or artifact.approval.decision is not ApprovalDecision.APPROVED
        or artifact.approval.policy_version != artifact.policy_version
        or artifact.approval.decided_at != artifact.created_at
    ):
        violations.append(
            PolicyViolation(
                code=ViolationCode.ARTIFACT_NOT_APPROVED,
                message="artifact approval is absent or not bound to this exact version",
                record_ids=(artifact.record_id,),
                field_path=("approval",),
            )
        )
    normative_support = False
    for reference in artifact.evidence_links.supporting:
        evidence = resolve_reference(index, reference)
        if isinstance(evidence, Evidence) and _NORMATIVE_CLAIMS & set(evidence.allowed_claim_types):
            normative_support = True
    if not normative_support:
        violations.append(
            PolicyViolation(
                code=ViolationCode.CLAIM_NOT_AUTHORIZED,
                message="durable behavioral artifact lacks direct normative support",
                record_ids=(artifact.record_id,),
            )
        )
    for claim_authority in artifact.claim_authorities.entries:
        authorized = False
        for evidence_ref in claim_authority.evidence_refs:
            evidence = resolve_reference(index, evidence_ref)
            if (
                isinstance(evidence, Evidence)
                and claim_authority.claim_type in evidence.allowed_claim_types
                and claim_authority.authority_class is evidence.authority_class
            ):
                authorized = True
        if not authorized:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.AUTHORITY_ESCALATION,
                    message=(
                        "artifact claim authority is not directly supported at the declared level"
                    ),
                    record_ids=(artifact.record_id,),
                    field_path=("claim_authorities", claim_authority.claim_type.value),
                )
            )
    candidate_outcomes: list[Outcome] = []
    case_ids: set[tuple[str, str]] = set()
    for candidate_reference in artifact.source_candidate_refs:
        candidate = resolve_reference(index, candidate_reference)
        if not isinstance(candidate, LessonCandidate):
            violations.append(_missing_reference(candidate_reference, artifact.record_id))
            continue
        candidate_decision = validate_lesson_candidate(
            candidate,
            materialized,
            required_use=PermittedUse.PROMOTION,
            require_approved=True,
        )
        violations.extend(candidate_decision.violations)
        if candidate.state not in {
            LessonCandidateState.APPROVED,
            LessonCandidateState.PROMOTED,
        }:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.CANDIDATE_NOT_APPROVED,
                    message="artifact source candidate is not approved",
                    record_ids=(artifact.record_id, candidate.record_id),
                )
            )
        violations.extend(
            _privacy_monotonicity_violations(
                owner_id=artifact.record_id,
                child=artifact.privacy,
                parent_id=candidate.record_id,
                parent=candidate.privacy,
            )
        )
        routing = route_lesson(candidate, policy_version=artifact.policy_version)
        if (
            not routing.eligible_for_artifact
            or routing.selected_route is not artifact.selected_route
            or routing.durable_artifact_kind is not artifact.artifact_kind
        ):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.ROUTING_MISMATCH,
                    message=(
                        "artifact does not match the deterministic least-invasive route "
                        "for its exact source candidate"
                    ),
                    record_ids=(artifact.record_id, candidate.record_id),
                    field_path=("selected_route",),
                )
            )
        if not scope_is_within(artifact.scope, candidate.scope):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.SCOPE_BROADENING,
                    message="artifact scope is broader than source candidate scope",
                    record_ids=(artifact.record_id, candidate.record_id),
                )
            )
        if not set(artifact.claim_authorities.entries) <= set(candidate.claim_authorities.entries):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.AUTHORITY_ESCALATION,
                    message="artifact introduced authority not present in its source candidate",
                    record_ids=(artifact.record_id, candidate.record_id),
                    field_path=("claim_authorities",),
                )
            )
        if not set(candidate.evidence_links.supporting) <= set(artifact.evidence_links.supporting):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVIDENCE_INCOMPLETE,
                    message="artifact omitted material supporting evidence from candidate",
                    record_ids=(artifact.record_id, candidate.record_id),
                )
            )
        for role in ("contradicting", "scope_limiting"):
            if not set(getattr(candidate.evidence_links, role)) <= set(
                getattr(artifact.evidence_links, role)
            ):
                violations.append(
                    PolicyViolation(
                        code=ViolationCode.EVIDENCE_INCOMPLETE,
                        message=f"artifact omitted {role} evidence from candidate",
                        record_ids=(artifact.record_id, candidate.record_id),
                    )
                )
        for case_ref in candidate.evaluation_case_refs:
            case_ids.add((case_ref.record_id, case_ref.record_version))
            case = resolve_reference(index, case_ref)
            if not isinstance(case, EvaluationCase):
                violations.append(_missing_reference(case_ref, artifact.record_id))
            elif case.partition is Partition.HELD_OUT:
                violations.append(
                    PolicyViolation(
                        code=ViolationCode.HELD_OUT_CONTAMINATION,
                        message="held-out evaluation case cannot support artifact construction",
                        record_ids=(artifact.record_id, case.record_id),
                    )
                )
            elif case.state not in {
                EvaluationCaseState.REVIEWED,
                EvaluationCaseState.APPROVED,
            }:
                violations.append(
                    PolicyViolation(
                        code=ViolationCode.EVALUATION_REQUIRED,
                        message="candidate evaluation case has not been reviewed",
                        record_ids=(artifact.record_id, case.record_id),
                    )
                )
        for outcome_ref in candidate.source_outcome_refs:
            outcome = resolve_reference(index, outcome_ref)
            if isinstance(outcome, Outcome):
                candidate_outcomes.append(outcome)
            else:
                violations.append(_missing_reference(outcome_ref, artifact.record_id))
    artifact_evidence_refs = {
        *artifact.evidence_links.supporting,
        *artifact.evidence_links.contradicting,
        *artifact.evidence_links.scope_limiting,
    }
    for evidence_ref in artifact_evidence_refs:
        evidence = resolve_reference(index, evidence_ref)
        if isinstance(evidence, Evidence):
            violations.extend(
                _privacy_monotonicity_violations(
                    owner_id=artifact.record_id,
                    child=artifact.privacy,
                    parent_id=evidence.record_id,
                    parent=evidence.privacy,
                )
            )
    attested_cases = {
        (item.case_ref.record_id, item.case_ref.record_version)
        for item in artifact.evaluation_attestations
        if item.result is EvaluationResult.PASSED
        and item.independent_of_proposer
        and item.partition is not Partition.HELD_OUT
    }
    for attestation in artifact.evaluation_attestations:
        subject = attestation.subject_ref
        if (
            subject.record_type.value != "artifact"
            or subject.record_id != artifact.record_id
            or subject.record_version != artifact.record_version
        ):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVALUATION_FAILED,
                    message="artifact evaluation attestation targets another record version",
                    record_ids=(artifact.record_id, subject.record_id),
                    field_path=("evaluation_attestations",),
                )
            )
        if (
            attestation.independent_of_proposer
            and attestation.evaluator.actor_id == artifact.created_by.actor_id
        ):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVALUATION_FAILED,
                    message="artifact proposer cannot be its independent evaluator",
                    record_ids=(artifact.record_id,),
                    field_path=("evaluation_attestations",),
                )
            )
    for outcome in candidate_outcomes:
        if outcome.kind not in _EVALUATION_FIRST_OUTCOMES:
            continue
        matching = {
            (case.record_id, case.record_version)
            for case in materialized
            if isinstance(case, EvaluationCase)
            and case.source_outcome_ref is not None
            and case.source_outcome_ref.record_id == outcome.record_id
            and case.source_outcome_ref.record_version == outcome.record_version
            and case.state in {EvaluationCaseState.REVIEWED, EvaluationCaseState.APPROVED}
            and case.partition is not Partition.HELD_OUT
        }
        if not matching or not (matching & case_ids & attested_cases):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.EVALUATION_REQUIRED,
                    message="correction/failure lacks a reviewed and passing evaluation-first case",
                    record_ids=(artifact.record_id, outcome.record_id),
                )
            )
    if artifact.privacy.review_state is not PrivacyReviewState.APPROVED:
        violations.append(
            PolicyViolation(
                code=ViolationCode.PRIVACY_NOT_APPROVED,
                message="artifact privacy review is not approved",
                record_ids=(artifact.record_id,),
            )
        )
    if any(item.resolution is ConflictResolution.UNRESOLVED for item in artifact.conflicts):
        violations.append(
            PolicyViolation(
                code=ViolationCode.UNRESOLVED_CONFLICT,
                message="artifact has unresolved conflicts",
                record_ids=(artifact.record_id,),
            )
        )
    return _decision(violations)


def validate_release_membership(
    release: Release, records: Iterable[VersionedRecord]
) -> PolicyDecision:
    index = index_records(records)
    violations: list[PolicyViolation] = []
    artifact_ids = [reference.record_id for reference in release.artifact_refs]
    if len(artifact_ids) != len(set(artifact_ids)):
        violations.append(
            PolicyViolation(
                code=ViolationCode.RELEASE_MEMBERSHIP_MISMATCH,
                message="release contains multiple versions of one artifact identity",
                record_ids=tuple(sorted(set(artifact_ids))),
            )
        )
    for reference in release.artifact_refs:
        artifact = resolve_reference(index, reference)
        if not isinstance(artifact, Artifact):
            violations.append(_missing_reference(reference, release.record_id))
        elif artifact.state is not ArtifactState.APPROVED:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.ARTIFACT_NOT_APPROVED,
                    message="release contains an unapproved or revoked artifact",
                    record_ids=(release.record_id, artifact.record_id),
                )
            )
    return _decision(violations)


_SENSITIVITY_RANK: dict[SensitivityClass, int] = {
    SensitivityClass.PUBLIC: 0,
    SensitivityClass.INTERNAL: 1,
    SensitivityClass.PRIVATE: 2,
    SensitivityClass.CONFIDENTIAL: 3,
    SensitivityClass.RESTRICTED: 4,
    SensitivityClass.PROHIBITED_SECRET: 5,
}


def _used_scope_dimensions(scope: Scope) -> set[str]:
    result = {"subject_ids"}
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
    if scope.valid_from is not None or scope.valid_until is not None:
        result.add("validity_window")
    return result


def validate_target_pack(pack: TargetPack, records: Iterable[VersionedRecord]) -> PolicyDecision:
    index = index_records(records)
    violations: list[PolicyViolation] = []
    release = resolve_reference(index, pack.release_ref)
    if not isinstance(release, Release):
        violations.append(_missing_reference(pack.release_ref, pack.record_id))
        return _decision(violations)
    release_refs = set(release.artifact_refs)
    entry_refs = {entry.artifact_ref for entry in pack.entries}
    omitted_refs = set(pack.omitted_artifact_refs)
    if pack.state is TargetPackState.VALIDATED and (
        entry_refs & omitted_refs or entry_refs | omitted_refs != release_refs
    ):
        violations.append(
            PolicyViolation(
                code=ViolationCode.RELEASE_MEMBERSHIP_MISMATCH,
                message="validated target pack entries must exactly match release membership",
                record_ids=(pack.record_id, release.record_id),
            )
        )
    for omitted_ref in pack.omitted_artifact_refs:
        artifact = resolve_reference(index, omitted_ref)
        if not isinstance(artifact, Artifact):
            violations.append(_missing_reference(omitted_ref, pack.record_id))
            continue
        target_scope = set(artifact.scope.target_families)
        if not target_scope or pack.target_profile.target_family in target_scope:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.MATERIAL_RENDERING_LOSS,
                    message="applicable release artifact was omitted from target pack",
                    record_ids=(pack.record_id, artifact.record_id),
                )
            )
    for entry in pack.entries:
        artifact = resolve_reference(index, entry.artifact_ref)
        if not isinstance(artifact, Artifact):
            violations.append(_missing_reference(entry.artifact_ref, pack.record_id))
            continue
        violations.extend(
            _privacy_monotonicity_violations(
                owner_id=pack.record_id,
                child=pack.privacy,
                parent_id=artifact.record_id,
                parent=artifact.privacy,
            )
        )
        if artifact.artifact_kind not in pack.target_profile.supported_artifact_kinds:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.TARGET_CAPABILITY_MISMATCH,
                    message=f"target does not support {artifact.artifact_kind.value}",
                    record_ids=(pack.record_id, artifact.record_id),
                )
            )
        unsupported_scope = _used_scope_dimensions(artifact.scope) - set(
            pack.target_profile.supported_scope_dimensions
        )
        if unsupported_scope:
            violations.append(
                PolicyViolation(
                    code=ViolationCode.TARGET_CAPABILITY_MISMATCH,
                    message="target cannot represent all artifact scope dimensions",
                    record_ids=(pack.record_id, artifact.record_id),
                    field_path=tuple(sorted(unsupported_scope)),
                )
            )
        all_evidence = {
            *artifact.evidence_links.supporting,
            *artifact.evidence_links.contradicting,
            *artifact.evidence_links.scope_limiting,
        }
        if not all_evidence <= set(entry.evidence_refs):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.TARGET_TRACE_INCOMPLETE,
                    message="rendered entry does not preserve complete artifact evidence trace",
                    record_ids=(pack.record_id, artifact.record_id),
                )
            )
        if entry.authority_digest != canonical_digest(artifact.claim_authorities):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.TARGET_TRACE_INCOMPLETE,
                    message="rendered entry changed or omitted claim-specific authority",
                    record_ids=(pack.record_id, artifact.record_id),
                    field_path=("authority_digest",),
                )
            )
        if (
            _SENSITIVITY_RANK[artifact.privacy.sensitivity]
            > _SENSITIVITY_RANK[pack.target_profile.maximum_sensitivity]
        ):
            violations.append(
                PolicyViolation(
                    code=ViolationCode.TARGET_CAPABILITY_MISMATCH,
                    message="artifact sensitivity exceeds target capability profile",
                    record_ids=(pack.record_id, artifact.record_id),
                )
            )
    if any(loss.materiality is LossMateriality.MATERIAL for loss in pack.losses):
        violations.append(
            PolicyViolation(
                code=ViolationCode.MATERIAL_RENDERING_LOSS,
                message="target pack declares a material rendering loss",
                record_ids=(pack.record_id,),
            )
        )
    return _decision(violations)
