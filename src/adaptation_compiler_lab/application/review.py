"""Immutable, human-attributable review workflows over persisted domain records."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from pydantic import BaseModel

from adaptation_compiler_lab.application.lifecycle import make_lifecycle_event
from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.domain import (
    ActorRef,
    Approval,
    ApprovalDecision,
    Artifact,
    ArtifactState,
    EvaluationAttestation,
    EvaluationCase,
    EvaluationCaseState,
    EvidenceLinks,
    ExactRecordRef,
    LessonCandidate,
    LessonCandidateState,
    PermittedUse,
    RecordKind,
    VersionedRecord,
)
from adaptation_compiler_lab.evaluation.policy import validate_evaluation_first
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.provenance import (
    PolicyDecision,
    PolicyViolation,
    index_records,
    validate_artifact_promotion,
    validate_evidence_links,
    validate_lesson_candidate,
    validate_lineage,
)
from adaptation_compiler_lab.release.transitions import validate_artifact_transition
from adaptation_compiler_lab.routing.policy import route_lesson
from adaptation_compiler_lab.sanitization import ExportSafetyError, assert_export_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class ReviewWorkflowError(ValueError):
    """Base error for a refused immutable review operation."""


class ReviewRecordNotFoundError(ReviewWorkflowError):
    """The exact subject-scoped input version is absent."""


class ReviewRecordTypeError(ReviewWorkflowError):
    """The exact input key names the wrong domain record type."""


class ReviewVersionError(ReviewWorkflowError):
    """A review attempted to reuse or move backward from a record version."""


class ReviewTransitionError(ReviewWorkflowError):
    """A requested transition is outside the closed review graph."""


class ReviewProvenanceError(ReviewWorkflowError):
    """An exact reference, attestation, or policy binding is invalid."""


class ReviewPolicyError(ReviewWorkflowError):
    """A fail-closed policy gate refused review approval."""

    def __init__(
        self,
        message: str,
        *,
        violations: tuple[PolicyViolation, ...] = (),
    ) -> None:
        super().__init__(message)
        self.violations = violations


_EVALUATION_CASE_TRANSITIONS = frozenset(
    {
        (EvaluationCaseState.CANDIDATE, EvaluationCaseState.APPROVED),
        (EvaluationCaseState.CANDIDATE, EvaluationCaseState.REJECTED),
        (EvaluationCaseState.REVIEWED, EvaluationCaseState.APPROVED),
        (EvaluationCaseState.REVIEWED, EvaluationCaseState.REJECTED),
    }
)

_LESSON_TRANSITIONS = frozenset(
    {
        (LessonCandidateState.PROPOSED, LessonCandidateState.APPROVED),
        (LessonCandidateState.PROPOSED, LessonCandidateState.REJECTED),
        (LessonCandidateState.REVIEWED, LessonCandidateState.APPROVED),
        (LessonCandidateState.REVIEWED, LessonCandidateState.REJECTED),
    }
)


class HumanReviewWorkflow:
    """Create and persist reviewed record versions without promotion or activation side effects."""

    def __init__(self, store: DomainRecordStore) -> None:
        self._store = store

    def approve_evaluation_candidate(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
    ) -> EvaluationCase:
        """Approve one exact candidate as a new ``EvaluationCase`` version."""

        return self._decide_evaluation_candidate(
            key,
            new_version=new_version,
            approval=approval,
            requested=EvaluationCaseState.APPROVED,
        )

    def reject_evaluation_candidate(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
    ) -> EvaluationCase:
        """Reject one exact candidate as a new ``EvaluationCase`` version."""

        return self._decide_evaluation_candidate(
            key,
            new_version=new_version,
            approval=approval,
            requested=EvaluationCaseState.REJECTED,
        )

    def propose_lesson(self, candidate: LessonCandidate) -> LessonCandidate:
        """Persist a proposal-only lesson after exact construction-side checks."""

        records = self._records()
        if candidate.state is not LessonCandidateState.PROPOSED or candidate.approval is not None:
            raise ReviewTransitionError(
                "lesson proposal must be in proposed state without an approval"
            )
        _require_absent(records, candidate)
        graph = _exact_provenance_graph(candidate, records)
        _require_allowed(
            "lesson proposal provenance",
            validate_lesson_candidate(
                candidate,
                graph,
                required_use=PermittedUse.CONSTRUCTION,
                require_approved=False,
            ),
        )
        _require_allowed(
            "lesson proposal evaluation links",
            validate_evaluation_first(
                candidate,
                graph,
                require_passing_attestation=False,
            ),
        )
        self._store.add(candidate)
        return candidate

    def decide_lesson(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
        evaluation_attestations: tuple[EvaluationAttestation, ...] | None = None,
    ) -> LessonCandidate:
        """Approve or reject a lesson proposal according to the human decision."""

        records = self._records()
        candidate = _require_record(records, key, LessonCandidate)
        _require_forward_version(records, candidate, new_version)
        requested = (
            LessonCandidateState.APPROVED
            if approval.decision is ApprovalDecision.APPROVED
            else LessonCandidateState.REJECTED
        )
        if (candidate.state, requested) not in _LESSON_TRANSITIONS:
            raise ReviewTransitionError(
                f"lesson transition {candidate.state.value}->{requested.value} is closed"
            )
        _validate_approval(candidate, approval, approval.decision)
        decided_attestations: tuple[EvaluationAttestation, ...] = ()
        if requested is LessonCandidateState.APPROVED:
            if not evaluation_attestations:
                raise ReviewProvenanceError(
                    "lesson approval requires exact approval-version attestations"
                )
            _validate_lesson_attestations(
                candidate,
                new_version=new_version,
                attestations=evaluation_attestations,
                records=records,
            )
            decided_attestations = evaluation_attestations
        decided = LessonCandidate.model_validate(
            {
                **candidate.model_dump(mode="python"),
                "record_version": new_version,
                "created_at": approval.decided_at,
                "state": requested,
                "approval": approval,
                "evaluation_attestations": decided_attestations,
            }
        )
        graph = _exact_provenance_graph(decided, records)
        _require_allowed("lesson decision lineage", validate_lineage(graph))
        if requested is LessonCandidateState.APPROVED:
            self._require_available_graph(graph, operation="lesson approval")
            _require_allowed(
                "lesson approval provenance",
                validate_lesson_candidate(
                    decided,
                    graph,
                    required_use=PermittedUse.PROMOTION,
                    require_approved=True,
                ),
            )
            _require_allowed(
                "lesson evaluation-first gate",
                validate_evaluation_first(
                    decided,
                    graph,
                    require_passing_attestation=True,
                ),
            )
        self._store.add(decided)
        return decided

    def approve_lesson(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
        evaluation_attestations: tuple[EvaluationAttestation, ...],
    ) -> LessonCandidate:
        """Approve a proposed lesson with exact approval-version evaluation results."""

        if approval.decision is not ApprovalDecision.APPROVED:
            raise ReviewProvenanceError("lesson approval requires an approved human decision")
        return self.decide_lesson(
            key,
            new_version=new_version,
            approval=approval,
            evaluation_attestations=evaluation_attestations,
        )

    def reject_lesson(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
    ) -> LessonCandidate:
        """Reject a proposed lesson with an attributable human decision."""

        if approval.decision is not ApprovalDecision.REJECTED:
            raise ReviewProvenanceError("lesson rejection requires a rejected human decision")
        return self.decide_lesson(
            key,
            new_version=new_version,
            approval=approval,
        )

    def propose_artifact(self, artifact: Artifact) -> Artifact:
        """Persist a draft-only artifact after exact construction-side checks."""

        records = self._records()
        if artifact.state is not ArtifactState.DRAFT:
            raise ReviewTransitionError("artifact proposal must be in draft state")
        if artifact.approval is not None or artifact.evaluation_attestations:
            raise ReviewTransitionError(
                "artifact proposal cannot carry approval or evaluation attestations"
            )
        _require_absent(records, artifact)
        graph = _exact_provenance_graph(artifact, records)
        _require_allowed("artifact proposal lineage", validate_lineage(graph))
        _require_allowed(
            "artifact proposal evidence",
            validate_evidence_links(
                artifact.evidence_links,
                index_records(graph),
                owner_id=artifact.record_id,
                required_use=PermittedUse.CONSTRUCTION,
            ),
        )
        for reference in artifact.source_candidate_refs:
            source = _resolve_exact(reference, _record_index(graph))
            if not isinstance(source, LessonCandidate) or source.state not in {
                LessonCandidateState.APPROVED,
                LessonCandidateState.PROMOTED,
            }:
                raise ReviewPolicyError(
                    "artifact proposal requires exact approved lesson candidate versions"
                )
            routing = route_lesson(source, policy_version=artifact.policy_version)
            if (
                not routing.eligible_for_artifact
                or routing.selected_route is not artifact.selected_route
                or routing.durable_artifact_kind is not artifact.artifact_kind
            ):
                raise ReviewPolicyError(
                    "artifact proposal does not match deterministic least-invasive routing"
                )
        self._persist_artifact_state(
            artifact,
            actor=artifact.created_by,
            reason="Persist reviewed artifact proposal",
        )
        return artifact

    def evaluate_artifact_proposal(
        self,
        key: RecordKey,
        *,
        new_version: str,
        evaluation_attestations: tuple[EvaluationAttestation, ...],
    ) -> Artifact:
        """Attach exact evaluation results to a draft as a new evaluated version."""

        records = self._records()
        artifact = _require_record(records, key, Artifact)
        _require_forward_version(records, artifact, new_version)
        _require_artifact_transition(artifact.state, ArtifactState.EVALUATED)
        if not evaluation_attestations:
            raise ReviewProvenanceError("artifact evaluation requires at least one attestation")
        _validate_artifact_attestations(
            artifact,
            new_version=new_version,
            attestations=evaluation_attestations,
            records=records,
        )
        evaluated_at = max(item.evaluated_at for item in evaluation_attestations)
        evaluated = Artifact.model_validate(
            {
                **artifact.model_dump(mode="python"),
                "record_version": new_version,
                "created_at": evaluated_at,
                "state": ArtifactState.EVALUATED,
                "evaluation_attestations": evaluation_attestations,
                "approval": None,
            }
        )
        graph = _exact_provenance_graph(evaluated, records)
        _require_allowed("artifact evaluation lineage", validate_lineage(graph))
        self._persist_artifact_state(
            evaluated,
            actor=evaluation_attestations[0].evaluator,
            reason="Persist evaluated artifact version",
        )
        return evaluated

    def approve_artifact_proposal(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
        evaluation_attestations: tuple[EvaluationAttestation, ...],
    ) -> Artifact:
        """Approve an evaluated artifact only after every durable-learning gate passes."""

        return self._decide_artifact(
            key,
            new_version=new_version,
            approval=approval,
            requested=ArtifactState.APPROVED,
            evaluation_attestations=evaluation_attestations,
        )

    def reject_artifact_proposal(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
    ) -> Artifact:
        """Reject an evaluated artifact as a new attributable record version."""

        return self._decide_artifact(
            key,
            new_version=new_version,
            approval=approval,
            requested=ArtifactState.REJECTED,
            evaluation_attestations=None,
        )

    def _decide_evaluation_candidate(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
        requested: EvaluationCaseState,
    ) -> EvaluationCase:
        records = self._records()
        candidate = _require_record(records, key, EvaluationCase)
        _require_forward_version(records, candidate, new_version)
        if (candidate.state, requested) not in _EVALUATION_CASE_TRANSITIONS:
            raise ReviewTransitionError(
                f"evaluation case transition {candidate.state.value}->{requested.value} is closed"
            )
        expected_decision = (
            ApprovalDecision.APPROVED
            if requested is EvaluationCaseState.APPROVED
            else ApprovalDecision.REJECTED
        )
        _validate_approval(candidate, approval, expected_decision)
        reviewed = EvaluationCase.model_validate(
            {
                **candidate.model_dump(mode="python"),
                "record_version": new_version,
                "created_at": approval.decided_at,
                "state": requested,
                "review": approval,
            }
        )
        graph = _exact_provenance_graph(reviewed, records)
        if requested is EvaluationCaseState.APPROVED:
            _require_allowed("evaluation candidate lineage", validate_lineage(graph))
            evidence_decision = validate_evidence_links(
                EvidenceLinks(supporting=reviewed.source_evidence_refs),
                index_records(graph),
                owner_id=reviewed.record_id,
                required_use=PermittedUse.DEVELOPMENT_EVALUATION,
            )
            _require_allowed("evaluation candidate evidence", evidence_decision)
        self._store.add(reviewed)
        return reviewed

    def _decide_artifact(
        self,
        key: RecordKey,
        *,
        new_version: str,
        approval: Approval,
        requested: ArtifactState,
        evaluation_attestations: tuple[EvaluationAttestation, ...] | None,
    ) -> Artifact:
        records = self._records()
        artifact = _require_record(records, key, Artifact)
        _require_forward_version(records, artifact, new_version)
        _require_artifact_transition(artifact.state, requested)
        expected_decision = (
            ApprovalDecision.APPROVED
            if requested is ArtifactState.APPROVED
            else ApprovalDecision.REJECTED
        )
        _validate_approval(artifact, approval, expected_decision)
        decided_attestations: tuple[EvaluationAttestation, ...] = ()
        if requested is ArtifactState.APPROVED:
            if not evaluation_attestations:
                raise ReviewProvenanceError(
                    "artifact approval requires exact approval-version attestations"
                )
            _validate_artifact_attestations(
                artifact,
                new_version=new_version,
                attestations=evaluation_attestations,
                records=records,
            )
            decided_attestations = evaluation_attestations
        decided = Artifact.model_validate(
            {
                **artifact.model_dump(mode="python"),
                "record_version": new_version,
                "created_at": approval.decided_at,
                "state": requested,
                "approval": approval,
                "evaluation_attestations": decided_attestations,
            }
        )
        graph = _exact_provenance_graph(decided, records)
        _require_allowed("artifact decision lineage", validate_lineage(graph))
        if requested is ArtifactState.APPROVED:
            _assert_artifact_text_safe(decided)
            self._require_available_graph(graph, operation="artifact promotion")
            graph_index = _record_index(graph)
            for reference in decided.source_candidate_refs:
                source = _resolve_exact(reference, graph_index)
                if source is None:
                    raise ReviewProvenanceError(
                        "artifact source candidate is absent from exact provenance graph"
                    )
                if not isinstance(source, LessonCandidate):
                    raise ReviewProvenanceError(
                        "artifact source reference does not resolve to a lesson candidate"
                    )
                _require_allowed(
                    "evaluation-first gate",
                    validate_evaluation_first(
                        source,
                        graph,
                        require_passing_attestation=True,
                    ),
                )
            _require_allowed(
                "artifact promotion gate",
                validate_artifact_promotion(decided, records),
            )
        self._persist_artifact_state(
            decided,
            actor=approval.approver,
            reason=f"Persist human-{requested.value} artifact version",
        )
        return decided

    def _records(self) -> tuple[VersionedRecord, ...]:
        return tuple(item.record for item in self._store.list())

    def _require_available_graph(
        self,
        graph: tuple[VersionedRecord, ...],
        *,
        operation: str,
    ) -> None:
        unavailable: list[str] = []
        for item in graph:
            state = self._store.current_lifecycle_state(
                RecordKey(
                    item.record_type.value,
                    item.record_id,
                    item.record_version,
                )
            )
            if state in {
                "excluded",
                "purged",
                "restricted",
                "revoked",
                "retired",
                "invalidated",
            }:
                unavailable.append(
                    f"{item.record_type.value}:{item.record_id}@{item.record_version}"
                )
        if unavailable:
            raise ReviewProvenanceError(
                f"{operation} depends on revoked material: " + ", ".join(sorted(unavailable))
            )

    def _persist_artifact_state(
        self,
        artifact: Artifact,
        *,
        actor: ActorRef,
        reason: str,
    ) -> None:
        key = RecordKey(
            kind=artifact.record_type.value,
            record_id=artifact.record_id,
            version=artifact.record_version,
        )
        event = make_lifecycle_event(
            event_id=(
                f"artifact-{artifact.record_id}-{artifact.record_version}-{artifact.state.value}"
            ),
            entity=key,
            from_state=None,
            to_state=artifact.state.value,
            previous_event_id=None,
            actor=actor,
            policy_version=artifact.policy_version,
            reason=reason,
            occurred_at=artifact.created_at,
        )
        self._store.add_with_lifecycle(artifact, (event,))


def _require_record[RecordT: VersionedRecord](
    records: tuple[VersionedRecord, ...],
    key: RecordKey,
    expected: type[RecordT],
) -> RecordT:
    for record in records:
        if (
            record.record_type.value == key.kind
            and record.record_id == key.record_id
            and record.record_version == key.version
        ):
            if not isinstance(record, expected):
                raise ReviewRecordTypeError(
                    f"review input {key.kind}:{key.record_id}@{key.version} has wrong type"
                )
            return record
    raise ReviewRecordNotFoundError(
        f"review input {key.kind}:{key.record_id}@{key.version} was not found"
    )


def _require_forward_version(
    records: tuple[VersionedRecord, ...],
    record: VersionedRecord,
    new_version: str,
) -> None:
    if _compare_semver(new_version, record.record_version) <= 0:
        raise ReviewVersionError("review output version must be newer than its exact input version")
    if any(
        item.record_type is record.record_type
        and item.record_id == record.record_id
        and item.record_version == new_version
        for item in records
    ):
        raise ReviewVersionError("review output version already exists")


def _require_absent(
    records: tuple[VersionedRecord, ...],
    record: VersionedRecord,
) -> None:
    if any(
        item.record_type is record.record_type
        and item.record_id == record.record_id
        and item.record_version == record.record_version
        for item in records
    ):
        raise ReviewVersionError("proposed exact record version already exists")


def _compare_semver(left: str, right: str) -> int:
    try:
        left_core, left_pre = _split_semver(left)
        right_core, right_pre = _split_semver(right)
    except (TypeError, ValueError) as error:
        raise ReviewVersionError("review output version must be semantic version syntax") from error
    if left_core != right_core:
        return 1 if left_core > right_core else -1
    if left_pre is None:
        return 0 if right_pre is None else 1
    if right_pre is None:
        return -1
    for left_part, right_part in zip(left_pre, right_pre, strict=False):
        if left_part == right_part:
            continue
        left_numeric = left_part.isdigit()
        right_numeric = right_part.isdigit()
        if left_numeric and right_numeric:
            return 1 if int(left_part) > int(right_part) else -1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return 1 if left_part > right_part else -1
    return (len(left_pre) > len(right_pre)) - (len(left_pre) < len(right_pre))


def _split_semver(value: str) -> tuple[tuple[int, int, int], tuple[str, ...] | None]:
    core_text, separator, prerelease = value.partition("-")
    core_parts = core_text.split(".")
    if (
        len(core_parts) != 3
        or any(not part.isdigit() for part in core_parts)
        or any(len(part) > 1 and part.startswith("0") for part in core_parts)
        or (separator and not prerelease)
    ):
        raise ValueError("invalid semantic version")
    prerelease_parts = tuple(prerelease.split(".")) if separator else None
    if prerelease_parts is not None and any(
        not part
        or not all(character.isalnum() or character == "-" for character in part)
        or (part.isdigit() and len(part) > 1 and part.startswith("0"))
        for part in prerelease_parts
    ):
        raise ValueError("invalid semantic prerelease")
    return (
        (int(core_parts[0]), int(core_parts[1]), int(core_parts[2])),
        prerelease_parts,
    )


def _validate_approval(
    record: VersionedRecord,
    approval: Approval,
    expected_decision: ApprovalDecision,
) -> None:
    if approval.decision is not expected_decision:
        raise ReviewProvenanceError(
            f"review requires an explicit {expected_decision.value} human decision"
        )
    if approval.approver.actor_id == record.created_by.actor_id:
        raise ReviewProvenanceError("record proposer cannot approve or reject its own proposal")
    if approval.policy_version != record.policy_version:
        raise ReviewProvenanceError(
            "approval policy version does not match the exact input version"
        )
    if approval.decided_at < record.created_at:
        raise ReviewProvenanceError("review decision cannot predate the exact input version")


def _require_artifact_transition(previous: ArtifactState, requested: ArtifactState) -> None:
    decision = validate_artifact_transition(previous, requested)
    if not decision.allowed:
        raise ReviewTransitionError(
            f"artifact transition {previous.value}->{requested.value} is closed"
        )


def _validate_artifact_attestations(
    artifact: Artifact,
    *,
    new_version: str,
    attestations: tuple[EvaluationAttestation, ...],
    records: tuple[VersionedRecord, ...],
) -> None:
    graph = _record_index(records)
    for attestation in attestations:
        subject = attestation.subject_ref
        if (
            subject.record_type is not RecordKind.ARTIFACT
            or subject.record_id != artifact.record_id
            or subject.record_version != new_version
            or subject.content_digest is not None
        ):
            raise ReviewProvenanceError(
                "evaluation attestation must identify the new artifact version "
                "without a self-digest"
            )
        case = _resolve_exact(attestation.case_ref, graph)
        if not isinstance(case, EvaluationCase):
            raise ReviewProvenanceError(
                "evaluation attestation case reference is missing or digest-mismatched"
            )
        if case.state not in {EvaluationCaseState.REVIEWED, EvaluationCaseState.APPROVED}:
            raise ReviewProvenanceError("evaluation attestation requires a reviewed case")
        if case.partition is not attestation.partition:
            raise ReviewProvenanceError("attestation partition does not match its exact case")
        if attestation.evaluated_at < max(artifact.created_at, case.created_at):
            raise ReviewProvenanceError("evaluation attestation predates its proposal or case")
        if (
            attestation.independent_of_proposer
            and attestation.evaluator.actor_id == artifact.created_by.actor_id
        ):
            raise ReviewProvenanceError(
                "self-evaluation cannot claim independence from the artifact proposer"
            )


def _validate_lesson_attestations(
    candidate: LessonCandidate,
    *,
    new_version: str,
    attestations: tuple[EvaluationAttestation, ...],
    records: tuple[VersionedRecord, ...],
) -> None:
    graph = _record_index(records)
    for attestation in attestations:
        subject = attestation.subject_ref
        if (
            subject.record_type is not RecordKind.LESSON_CANDIDATE
            or subject.record_id != candidate.record_id
            or subject.record_version != new_version
            or subject.content_digest is not None
        ):
            raise ReviewProvenanceError(
                "evaluation attestation must identify the new lesson version without a self-digest"
            )
        case = _resolve_exact(attestation.case_ref, graph)
        if not isinstance(case, EvaluationCase):
            raise ReviewProvenanceError(
                "lesson attestation case reference is missing or digest-mismatched"
            )
        if case.state not in {EvaluationCaseState.REVIEWED, EvaluationCaseState.APPROVED}:
            raise ReviewProvenanceError("lesson attestation requires a reviewed case")
        if case.partition is not attestation.partition:
            raise ReviewProvenanceError("lesson attestation partition does not match its case")
        if attestation.evaluated_at < max(candidate.created_at, case.created_at):
            raise ReviewProvenanceError("lesson attestation predates its proposal or case")
        if (
            attestation.independent_of_proposer
            and attestation.evaluator.actor_id == candidate.created_by.actor_id
        ):
            raise ReviewProvenanceError(
                "self-evaluation cannot claim independence from the lesson proposer"
            )


def _record_index(
    records: tuple[VersionedRecord, ...],
) -> dict[tuple[RecordKind, str, str], VersionedRecord]:
    return {
        (record.record_type, record.record_id, record.record_version): record for record in records
    }


def _resolve_exact(
    reference: ExactRecordRef,
    records: Mapping[tuple[RecordKind, str, str], VersionedRecord],
) -> VersionedRecord | None:
    record = records.get((reference.record_type, reference.record_id, reference.record_version))
    if record is None:
        return None
    if reference.content_digest is not None and reference.content_digest != canonical_digest(
        record
    ):
        return None
    return record


def _exact_provenance_graph(
    root: VersionedRecord,
    records: tuple[VersionedRecord, ...],
) -> tuple[VersionedRecord, ...]:
    index = _record_index((*records, root))
    graph: dict[tuple[RecordKind, str, str], VersionedRecord] = {}

    def visit(record: VersionedRecord) -> None:
        key = (record.record_type, record.record_id, record.record_version)
        if key in graph:
            return
        graph[key] = record
        for reference in _walk_refs(record):
            target = _resolve_exact(reference, index)
            if target is None:
                raise ReviewProvenanceError(
                    "exact provenance reference is missing or digest-mismatched: "
                    f"{reference.record_type.value}:{reference.record_id}@"
                    f"{reference.record_version}"
                )
            visit(target)

    visit(root)
    return tuple(graph[key] for key in sorted(graph, key=lambda item: tuple(map(str, item))))


def _walk_refs(value: object) -> Iterator[ExactRecordRef]:
    if isinstance(value, ExactRecordRef):
        yield value
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _walk_refs(getattr(value, name))
        return
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield from _walk_refs(value[key])
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_refs(item)


def _require_allowed(label: str, decision: PolicyDecision) -> None:
    if decision.allowed:
        return
    codes = ", ".join(sorted({item.code.value for item in decision.violations}))
    raise ReviewPolicyError(
        f"{label} failed: {codes}",
        violations=decision.violations,
    )


def _assert_artifact_text_safe(artifact: Artifact) -> None:
    try:
        assert_export_safe(canonical_json(artifact), label="artifact candidate")
    except ExportSafetyError as error:
        raise ReviewPolicyError(str(error)) from error
