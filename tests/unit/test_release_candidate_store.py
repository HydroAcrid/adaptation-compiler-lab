"""Persistent application-level ReleaseCandidate snapshot store tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.application.release_candidate_store import (
    RELEASE_CANDIDATE_SNAPSHOT_KIND,
    ReleaseCandidateSnapshotConflictError,
    ReleaseCandidateSnapshotStore,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ConstructionBoundary,
    ReleaseCandidateState,
)
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.release.proposals import (
    ReleaseCandidate,
    propose_release_candidate,
    transition_release_candidate,
)
from adaptation_compiler_lab.serialization import canonical_json

NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)
CREATOR = ActorRef(actor_id="creator", kind=ActorKind.AGENT, version="1.0.0")
REVIEWER = ActorRef(actor_id="reviewer", kind=ActorKind.HUMAN_REVIEWER)


def _proposed() -> ReleaseCandidate:
    return propose_release_candidate(
        candidate_id="candidate-1",
        candidate_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        artifact_refs=(),
        schema_versions=("1.0.0",),
        policy_versions=("1.0.0",),
        construction_boundary=ConstructionBoundary(
            construction_cutoff=NOW,
            split_manifest_digest="sha256:" + "a" * 64,
            custody_policy_version="1.0.0",
        ),
        proposal_disposition_id="proposal-1",
        proposal_rationale="persist candidate across CLI processes",
    )


def _evaluated(candidate: ReleaseCandidate) -> ReleaseCandidate:
    return transition_release_candidate(
        candidate,
        requested=ReleaseCandidateState.EVALUATED,
        disposition_id="evaluation-1",
        decided_at=NOW + timedelta(minutes=1),
        actor=REVIEWER,
        rationale="release gates evaluated",
        gate_report_digest="sha256:" + "b" * 64,
    )


def _factory(tmp_path: Path) -> SqliteUnitOfWorkFactory:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    return factory


def test_put_get_and_list_round_trip_canonical_snapshots(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    store = ReleaseCandidateSnapshotStore(factory, subject_id="subject-kevin")
    proposed = _proposed()
    evaluated = _evaluated(proposed)

    proposed_snapshot = store.put(proposed)
    evaluated_snapshot = store.put(evaluated)

    assert store.require(proposed_snapshot.key) == proposed_snapshot
    assert store.require(evaluated_snapshot.key) == evaluated_snapshot
    assert store.list(candidate_id="candidate-1") == (
        proposed_snapshot,
        evaluated_snapshot,
    )
    assert store.list(state=ReleaseCandidateState.EVALUATED) == (evaluated_snapshot,)
    with factory(write=False) as unit_of_work:
        stored = unit_of_work.records.list_records(
            kind=RELEASE_CANDIDATE_SNAPSHOT_KIND,
            subject_id="subject-kevin",
        )
    assert tuple(item.canonical_json for item in stored) == (
        canonical_json(proposed),
        canonical_json(evaluated),
    )


def test_exact_repeat_is_idempotent_but_divergent_key_is_rejected(tmp_path: Path) -> None:
    store = ReleaseCandidateSnapshotStore(_factory(tmp_path), subject_id="subject-kevin")
    proposed = _proposed()
    first = store.put(proposed)

    assert store.put(proposed) == first
    divergent = proposed.model_copy(update={"target_compatibility": ("changed-target",)})
    with pytest.raises(ReleaseCandidateSnapshotConflictError):
        store.put(divergent)


def test_subject_namespaces_are_isolated_even_for_identical_candidate_ids(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    kevin = ReleaseCandidateSnapshotStore(factory, subject_id="subject-kevin")
    other = ReleaseCandidateSnapshotStore(factory, subject_id="subject-other")
    candidate = _proposed()

    kevin_snapshot = kevin.put(candidate)
    other_snapshot = other.put(candidate)

    assert kevin.list() == (kevin_snapshot,)
    assert other.list() == (other_snapshot,)
    assert kevin.require(kevin_snapshot.key).candidate == candidate
    assert other.require(other_snapshot.key).candidate == candidate


def test_auxiliary_candidate_rows_cannot_poison_domain_record_listing(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    ReleaseCandidateSnapshotStore(factory, subject_id="subject-kevin").put(_proposed())
    domain_store = DomainRecordStore(factory, subject_id="subject-kevin")

    assert domain_store.list() == ()
    assert domain_store.list(record_kind=RELEASE_CANDIDATE_SNAPSHOT_KIND) == ()
