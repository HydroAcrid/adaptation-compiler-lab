"""Release service tests using a real temporary SQLite ledger."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ApprovalDecision,
    ArtifactRef,
    ConstructionBoundary,
    Release,
    ReleaseCandidateState,
)
from adaptation_compiler_lab.persistence.errors import RecordConflictError
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.release.proposals import ReleaseCandidate, propose_release_candidate
from adaptation_compiler_lab.release.service import ReleaseService, ReleaseServiceError

NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)
CREATOR = ActorRef(actor_id="creator", kind=ActorKind.AGENT, version="1.0.0")
REVIEWER = ActorRef(actor_id="reviewer", kind=ActorKind.HUMAN_REVIEWER)
BOUNDARY = ConstructionBoundary(
    construction_cutoff=NOW,
    split_manifest_digest="sha256:" + "a" * 64,
    custody_policy_version="1.0.0",
)


def _candidate(*, artifact_refs: tuple[ArtifactRef, ...] = ()) -> ReleaseCandidate:
    return propose_release_candidate(
        candidate_id="candidate-1",
        candidate_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        artifact_refs=artifact_refs,
        schema_versions=("1.0.0",),
        policy_versions=("1.0.0",),
        construction_boundary=BOUNDARY,
        proposal_disposition_id="proposal-1",
        proposal_rationale="propose release",
    )


def _approval() -> Approval:
    return Approval(
        decision=ApprovalDecision.APPROVED,
        approver=REVIEWER,
        decided_at=NOW + timedelta(minutes=2),
        policy_version="1.0.0",
        rationale="approve gate-passing candidate",
    )


def test_empty_release_flow_persists_one_immutable_manifest(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    service = ReleaseService(factory, subject_id="subject-kevin")
    proposed = _candidate()
    evaluation = service.evaluate(
        proposed,
        evaluated_at=NOW + timedelta(minutes=1),
        evaluator=REVIEWER,
        disposition_id="evaluation-1",
        rationale="empty release gates pass",
    )
    approved = service.approve(
        evaluation,
        approval=_approval(),
        disposition_id="approval-1",
    )

    result = service.freeze(
        approved,
        release_id="release-1",
        record_version="1.0.0",
        release_version="1.0.0",
        released_at=NOW + timedelta(minutes=3),
        created_by=CREATOR,
        disposition_id="freeze-1",
        rationale="freeze exact empty release",
    )

    assert result.candidate.state is ReleaseCandidateState.FROZEN
    assert result.release.is_empty_release
    stored = DomainRecordStore(factory, subject_id="subject-kevin").require(
        RecordKey("release", "release-1", "1.0.0")
    )
    assert isinstance(stored.record, Release)
    assert stored.record == result.release
    with factory(write=False) as unit_of_work:
        assert unit_of_work.lifecycle.current_state(stored.key) == "released"


def test_failed_gates_cannot_be_approved(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    service = ReleaseService(factory, subject_id="subject-kevin")
    missing = ArtifactRef(
        record_id="missing-artifact",
        record_version="1.0.0",
        content_digest="sha256:" + "f" * 64,
    )
    evaluation = service.evaluate(
        _candidate(artifact_refs=(missing,)),
        evaluated_at=NOW + timedelta(minutes=1),
        evaluator=REVIEWER,
        disposition_id="evaluation-1",
        rationale="evaluate missing artifact",
    )

    assert not evaluation.report.passed
    with pytest.raises(ReleaseServiceError, match="cannot be approved"):
        service.approve(
            evaluation,
            approval=_approval(),
            disposition_id="approval-1",
        )


def test_freeze_never_rewrites_existing_release_version(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    service = ReleaseService(factory, subject_id="subject-kevin")
    evaluation = service.evaluate(
        _candidate(),
        evaluated_at=NOW + timedelta(minutes=1),
        evaluator=REVIEWER,
        disposition_id="evaluation-1",
        rationale="evaluate",
    )
    approved = service.approve(evaluation, approval=_approval(), disposition_id="approval-1")
    service.freeze(
        approved,
        release_id="release-1",
        record_version="1.0.0",
        release_version="1.0.0",
        released_at=NOW + timedelta(minutes=3),
        created_by=CREATOR,
        disposition_id="freeze-1",
        rationale="first freeze",
    )

    with pytest.raises(RecordConflictError):
        service.freeze(
            approved,
            release_id="release-1",
            record_version="1.0.0",
            release_version="2.0.0",
            released_at=NOW + timedelta(minutes=4),
            created_by=CREATOR,
            disposition_id="freeze-2",
            rationale="attempt rewrite",
        )
