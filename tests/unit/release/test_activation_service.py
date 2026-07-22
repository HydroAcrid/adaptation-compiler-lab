"""Activation is an append-only pointer and rollback preserves history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from adaptation_compiler_lab.application.lifecycle import make_lifecycle_event
from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ApprovalDecision,
    Artifact,
    ArtifactRef,
    Release,
    ReleaseRef,
    TargetPack,
)
from adaptation_compiler_lab.persistence import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.release.activation import (
    ActivationAction,
    ActivationError,
    ActivationService,
)
from adaptation_compiler_lab.serialization import record_ref
from tests.unit.test_domain_policy import SyntheticGraph, synthetic_graph

NOW = datetime(2026, 7, 22, 18, 0, tzinfo=UTC)


def approval(*, at: datetime, rationale: str) -> Approval:
    return Approval(
        decision=ApprovalDecision.APPROVED,
        approver=ActorRef(actor_id="reviewer-1", kind=ActorKind.HUMAN_REVIEWER),
        decided_at=at,
        policy_version="1.0.0",
        rationale=rationale,
    )


def _persist_graph(
    factory: SqliteUnitOfWorkFactory,
    graph: SyntheticGraph,
    *,
    artifact: Artifact | None = None,
    release: Release | None = None,
    target_pack: TargetPack | None = None,
) -> tuple[RecordKey, RecordKey]:
    selected_artifact = graph.artifact if artifact is None else artifact
    selected_release = graph.release if release is None else release
    selected_pack = graph.target_pack if target_pack is None else target_pack
    DomainRecordStore(factory, subject_id="user-kevin").add_many(
        (
            graph.evidence,
            graph.task,
            graph.outcome,
            graph.evaluation_case,
            graph.candidate,
            selected_artifact,
            selected_release,
            selected_pack,
        )
    )
    artifact_key = RecordKey(
        "artifact", selected_artifact.record_id, selected_artifact.record_version
    )
    release_key = RecordKey("release", selected_release.record_id, selected_release.record_version)
    pack_key = RecordKey("target_pack", selected_pack.record_id, selected_pack.record_version)
    _append_lifecycle_state(factory, key=artifact_key, state="approved", at=NOW)
    _append_lifecycle_state(factory, key=release_key, state="released", at=NOW)
    _append_lifecycle_state(factory, key=pack_key, state="built", at=NOW)
    _append_lifecycle_state(factory, key=pack_key, state="validated", at=NOW)
    return release_key, pack_key


def _append_lifecycle_state(
    factory: SqliteUnitOfWorkFactory,
    *,
    key: RecordKey,
    state: str,
    at: datetime,
) -> None:
    with factory(write=True) as unit_of_work:
        history = unit_of_work.lifecycle.history(key)
        previous = history[-1] if history else None
        event = make_lifecycle_event(
            event_id=f"{key.kind}-{key.record_id}-{key.version}-{state}-{len(history) + 1}",
            entity=key,
            from_state=None if previous is None else previous.to_state,
            to_state=state,
            previous_event_id=None if previous is None else previous.event_id,
            actor=ActorRef(actor_id="reviewer-1", kind=ActorKind.HUMAN_REVIEWER),
            policy_version="1.0.0",
            reason=f"Synthetic {state} lifecycle decision.",
            occurred_at=at,
        )
        unit_of_work.lifecycle.append(event)
        unit_of_work.commit()


def _expired_graph_versions(
    graph: SyntheticGraph,
) -> tuple[Artifact, Release, TargetPack]:
    artifact = Artifact.model_validate(
        {
            **graph.artifact.model_dump(mode="python"),
            "expires_at": NOW - timedelta(minutes=1),
        }
    )
    artifact_ref = cast(ArtifactRef, record_ref(artifact))
    release = Release.model_validate(
        {
            **graph.release.model_dump(mode="python"),
            "artifact_refs": (artifact_ref,),
        }
    )
    release_ref = cast(ReleaseRef, record_ref(release))
    entry = graph.target_pack.entries[0].model_copy(update={"artifact_ref": artifact_ref})
    target_pack = TargetPack.model_validate(
        {
            **graph.target_pack.model_dump(mode="python"),
            "release_ref": release_ref,
            "entries": (entry,),
        }
    )
    return artifact, release, target_pack


def test_canary_activation_and_rollback_are_distinct_auditable_events(tmp_path: Path) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    release, pack = _persist_graph(factory, graph)
    service = ActivationService(factory)

    canary = service.canary(
        environment_id="synthetic-environment",
        release=release,
        target_pack=pack,
        approval=approval(at=NOW, rationale="Synthetic canary review."),
    )
    active = service.activate(
        environment_id="synthetic-environment",
        release=release,
        target_pack=pack,
        approval=approval(
            at=NOW + timedelta(minutes=1), rationale="Synthetic activation approval."
        ),
    )
    rolled_back = service.rollback(
        environment_id="synthetic-environment",
        release=release,
        target_pack=pack,
        approval=approval(at=NOW + timedelta(minutes=2), rationale="Synthetic rollback exercise."),
    )

    assert canary.action is ActivationAction.CANARY
    assert active.action is ActivationAction.ACTIVATE
    assert rolled_back.action is ActivationAction.ROLLBACK
    assert service.current("synthetic-environment") == rolled_back
    with factory(write=False) as unit_of_work:
        history = unit_of_work.activations.history("synthetic-environment")
    assert tuple(event.action for event in history) == ("canary", "activate", "rollback")
    assert len({event.event_id for event in history}) == 3


def test_activation_service_enforces_the_closed_state_graph(tmp_path: Path) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    release, pack = _persist_graph(factory, graph)
    service = ActivationService(factory)
    service.activate(
        environment_id="synthetic-environment",
        release=release,
        target_pack=pack,
        approval=approval(at=NOW, rationale="Activate the reviewed pack."),
    )

    with pytest.raises(ActivationError, match="active -> canary"):
        service.canary(
            environment_id="synthetic-environment",
            release=release,
            target_pack=pack,
            approval=approval(
                at=NOW + timedelta(minutes=1),
                rationale="Invalid attempt to move backward into canary.",
            ),
        )


def test_activation_rejects_a_human_rejection_decision(tmp_path: Path) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    store = DomainRecordStore(factory, subject_id="user-kevin")
    store.add_many(
        (
            graph.evidence,
            graph.task,
            graph.outcome,
            graph.evaluation_case,
            graph.candidate,
            graph.artifact,
            graph.release,
            graph.target_pack,
        )
    )
    rejection = Approval(
        decision=ApprovalDecision.REJECTED,
        approver=ActorRef(actor_id="reviewer-1", kind=ActorKind.HUMAN_REVIEWER),
        decided_at=NOW,
        policy_version="1.0.0",
        rationale="Do not activate this synthetic pack.",
    )

    with pytest.raises(ActivationError, match="require human approval"):
        ActivationService(factory).activate(
            environment_id="synthetic-environment",
            release=RecordKey("release", graph.release.record_id, graph.release.record_version),
            target_pack=RecordKey(
                "target_pack", graph.target_pack.record_id, graph.target_pack.record_version
            ),
            approval=rejection,
        )


def test_activation_rejects_records_without_authoritative_lifecycle(tmp_path: Path) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    DomainRecordStore(factory, subject_id="user-kevin").add_many(
        (
            graph.evidence,
            graph.task,
            graph.outcome,
            graph.evaluation_case,
            graph.candidate,
            graph.artifact,
            graph.release,
            graph.target_pack,
        )
    )

    with pytest.raises(ActivationError, match="release in state missing"):
        ActivationService(factory).activate(
            environment_id="missing-lifecycle-environment",
            release=RecordKey("release", graph.release.record_id, graph.release.record_version),
            target_pack=RecordKey(
                "target_pack", graph.target_pack.record_id, graph.target_pack.record_version
            ),
            approval=approval(at=NOW, rationale="Attempt activation without lifecycle authority."),
        )


def test_activation_rejects_a_hand_built_inconsistent_target_pack(tmp_path: Path) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    tampered_entry = graph.target_pack.entries[0].model_copy(
        update={"authority_digest": "sha256:" + "0" * 64}
    )
    tampered_pack = TargetPack.model_validate(
        {
            **graph.target_pack.model_dump(mode="python"),
            "record_id": "pack-tampered",
            "entries": (tampered_entry,),
        }
    )
    release, _ = _persist_graph(factory, graph, target_pack=tampered_pack)

    with pytest.raises(ActivationError, match="target pack policy failed: target_trace"):
        ActivationService(factory).canary(
            environment_id="tampered-pack-environment",
            release=release,
            target_pack=RecordKey(
                "target_pack",
                tampered_pack.record_id,
                tampered_pack.record_version,
            ),
            approval=approval(at=NOW, rationale="Attempt to activate a hand-built pack."),
        )


@pytest.mark.parametrize("state", ["expired", "rejected", "revoked", "withdrawn"])
def test_activation_refuses_terminal_member_lifecycle_state(
    tmp_path: Path,
    state: str,
) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    release, pack = _persist_graph(factory, graph)
    artifact_key = RecordKey(
        "artifact",
        graph.artifact.record_id,
        graph.artifact.record_version,
    )
    _append_lifecycle_state(factory, key=artifact_key, state=state, at=NOW)

    with pytest.raises(ActivationError, match=f"artifact in state {state}"):
        ActivationService(factory).canary(
            environment_id=f"{state}-member-environment",
            release=release,
            target_pack=pack,
            approval=approval(at=NOW, rationale=f"Attempt activation after {state}."),
        )


def test_rollback_revalidates_a_previously_activated_pair(tmp_path: Path) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    release, pack = _persist_graph(factory, graph)
    service = ActivationService(factory)
    service.canary(
        environment_id="rollback-revalidation-environment",
        release=release,
        target_pack=pack,
        approval=approval(at=NOW, rationale="Initial reviewed canary."),
    )
    active = service.activate(
        environment_id="rollback-revalidation-environment",
        release=release,
        target_pack=pack,
        approval=approval(at=NOW + timedelta(minutes=1), rationale="Initial activation."),
    )
    _append_lifecycle_state(
        factory,
        key=RecordKey(
            "artifact",
            graph.artifact.record_id,
            graph.artifact.record_version,
        ),
        state="revoked",
        at=NOW + timedelta(minutes=2),
    )

    with pytest.raises(ActivationError, match="artifact in state revoked"):
        service.rollback(
            environment_id="rollback-revalidation-environment",
            release=release,
            target_pack=pack,
            approval=approval(
                at=NOW + timedelta(minutes=3),
                rationale="Attempt rollback to a newly revoked artifact.",
            ),
        )
    assert service.current("rollback-revalidation-environment") == active


def test_activation_rechecks_artifact_expiry_at_approval_time(tmp_path: Path) -> None:
    graph = synthetic_graph()
    artifact, release_record, pack_record = _expired_graph_versions(graph)
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    release, pack = _persist_graph(
        factory,
        graph,
        artifact=artifact,
        release=release_record,
        target_pack=pack_record,
    )

    with pytest.raises(ActivationError, match="expired artifact artifact-1"):
        ActivationService(factory).activate(
            environment_id="expired-artifact-environment",
            release=release,
            target_pack=pack,
            approval=approval(at=NOW, rationale="Attempt activation after artifact expiry."),
        )
