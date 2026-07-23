"""Withdrawal, recall cascade, purge, atomic deactivation, and idempotency tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from adaptation_compiler_lab.application.governance import (
    EvidenceGovernanceError,
    validate_evidence_governance,
)
from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.domain import PayloadReference, Scope, VersionedRecord
from adaptation_compiler_lab.governance import (
    GovernanceObjectKind,
    InvalidationAction,
    InvalidationEvent,
    RecallTarget,
    RecallTargetKind,
    SignerIdentity,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    governance_ref,
)
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
)
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.recall import RecallError, RecallService
from adaptation_compiler_lab.release.activation import ActivationAction, ActivationService
from adaptation_compiler_lab.serialization import canonical_digest, record_ref
from tests.unit.release.test_activation_service import (
    _append_lifecycle_state,
    _persist_graph,
    approval,
)
from tests.unit.test_domain_policy import synthetic_graph
from tests.unit.test_governance import _capture, _consent, _evidence, _identity

PREVIEW_AT = datetime(2026, 7, 22, 19, 0, tzinfo=UTC)
COMPLETE_AT = PREVIEW_AT + timedelta(minutes=15)


def _recall_identity(
    ledger: GovernanceLedger,
    *,
    subject_id: str = "user-kevin",
) -> tuple[GovernanceSigner, SignerIdentity]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id=f"{subject_id}-recall-identity",
        subject_id=subject_id,
    )
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CUSTODY,),
        created_at=PREVIEW_AT - timedelta(hours=1),
        expires_at=PREVIEW_AT + timedelta(days=30),
    )
    ledger.add(identity)
    return signer, identity


def _target(kind: RecallTargetKind, record: VersionedRecord) -> RecallTarget:
    return RecallTarget(
        target_kind=kind,
        object_id=record.record_id,
        record_version=record.record_version,
        content_digest=canonical_digest(record),
    )


def test_restricting_evidence_recalls_release_pack_and_active_pointer_atomically(
    tmp_path: Path,
) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    release_key, pack_key = _persist_graph(factory, graph)
    ActivationService(factory).activate(
        environment_id="synthetic-environment",
        release=release_key,
        target_pack=pack_key,
        approval=approval(
            at=PREVIEW_AT - timedelta(minutes=30),
            rationale="Activate before the synthetic recall exercise.",
        ),
    )
    ledger = GovernanceLedger(Path(factory.path), subject_id="user-kevin")
    signer, _ = _recall_identity(ledger)
    service = RecallService(factory, subject_id="user-kevin")

    impact = service.preflight(
        impact_id="impact-active-cascade",
        root_target=_target(RecallTargetKind.EVIDENCE, graph.evidence),
        requested_action=InvalidationAction.RESTRICT_EVIDENCE,
        generated_at=PREVIEW_AT,
        policy_version="1.0.0",
        signer=signer,
    )
    affected_kinds = {entry.target.target_kind for entry in impact.affected}
    assert {
        RecallTargetKind.EVIDENCE,
        RecallTargetKind.ARTIFACT,
        RecallTargetKind.RELEASE,
        RecallTargetKind.TARGET_PACK,
        RecallTargetKind.ACTIVATION,
    } <= affected_kinds
    with pytest.raises(RecallError, match="bound to another preflight"):
        service.preflight(
            impact_id=impact.impact_id,
            root_target=_target(RecallTargetKind.EVIDENCE, graph.evidence),
            requested_action=InvalidationAction.PURGE_EVIDENCE,
            generated_at=PREVIEW_AT,
            policy_version="1.0.0",
            signer=signer,
        )

    report = service.execute(
        impact_id=impact.impact_id,
        confirmation_digest=canonical_digest(impact),
        completed_at=COMPLETE_AT,
        reason="Withdraw the synthetic correction and every dependent adaptation.",
        signer=signer,
    )

    with factory(write=False) as unit_of_work:
        assert (
            unit_of_work.lifecycle.current_state(
                RecordKey("evidence", graph.evidence.record_id, graph.evidence.record_version)
            )
            == "restricted"
        )
        assert (
            unit_of_work.lifecycle.current_state(
                RecordKey("artifact", graph.artifact.record_id, graph.artifact.record_version)
            )
            == "revoked"
        )
        assert unit_of_work.lifecycle.current_state(release_key) == "retired"
        assert unit_of_work.lifecycle.current_state(pack_key) == "invalidated"
        current = unit_of_work.activations.current("synthetic-environment")
    assert current is not None
    assert current.action == ActivationAction.DEACTIVATE.value
    assert current.release is None and current.target_pack is None
    assert report.deactivated_environment_ids == ("synthetic-environment",)

    repeated = service.execute(
        impact_id=impact.impact_id,
        confirmation_digest=canonical_digest(impact),
        completed_at=COMPLETE_AT + timedelta(hours=1),
        reason="An exact repeat is an idempotent no-op.",
        signer=signer,
    )
    assert repeated == report
    with pytest.raises(RecallError, match="confirmation digest"):
        service.execute(
            impact_id=impact.impact_id,
            confirmation_digest="sha256:" + "0" * 64,
            completed_at=COMPLETE_AT + timedelta(hours=2),
            reason="A repeat still requires the original exact confirmation.",
            signer=signer,
        )


def test_graph_change_after_preflight_blocks_every_recall_write(tmp_path: Path) -> None:
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    release_key, pack_key = _persist_graph(factory, graph)
    ActivationService(factory).activate(
        environment_id="synthetic-environment",
        release=release_key,
        target_pack=pack_key,
        approval=approval(
            at=PREVIEW_AT - timedelta(minutes=30),
            rationale="Activate before stale-impact testing.",
        ),
    )
    ledger = GovernanceLedger(Path(factory.path), subject_id="user-kevin")
    signer, _ = _recall_identity(ledger)
    service = RecallService(factory, subject_id="user-kevin")
    impact = service.preflight(
        impact_id="impact-stale",
        root_target=_target(RecallTargetKind.ARTIFACT, graph.artifact),
        requested_action=InvalidationAction.REVOKE_ARTIFACT,
        generated_at=PREVIEW_AT,
        policy_version="1.0.0",
        signer=signer,
    )
    artifact_key = RecordKey("artifact", graph.artifact.record_id, graph.artifact.record_version)
    _append_lifecycle_state(
        factory,
        key=artifact_key,
        state="superseded",
        at=PREVIEW_AT + timedelta(minutes=1),
    )

    with pytest.raises(RecallError, match="graph changed"):
        service.execute(
            impact_id=impact.impact_id,
            confirmation_digest=canonical_digest(impact),
            completed_at=COMPLETE_AT,
            reason="This stale confirmation must fail.",
            signer=signer,
        )

    with factory(write=False) as unit_of_work:
        assert unit_of_work.lifecycle.current_state(release_key) == "released"
        current = unit_of_work.activations.current("synthetic-environment")
    assert current is not None and current.release == release_key
    assert not ledger.list(GovernanceObjectKind.INVALIDATION_EVENT)


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@given(
    case=st.sampled_from(
        [
            (
                RecallTargetKind.EVIDENCE,
                InvalidationAction.RESTRICT_EVIDENCE,
                "restricted",
            ),
            (
                RecallTargetKind.ARTIFACT,
                InvalidationAction.REVOKE_ARTIFACT,
                "revoked",
            ),
            (
                RecallTargetKind.RELEASE,
                InvalidationAction.RETIRE_RELEASE,
                "retired",
            ),
            (
                RecallTargetKind.TARGET_PACK,
                InvalidationAction.INVALIDATE_TARGET_PACK,
                "invalidated",
            ),
        ]
    ),
    nonce=st.integers(min_value=0, max_value=1_000_000),
)
def test_any_active_dependency_root_deactivates_its_pointer(
    tmp_path: Path,
    case: tuple[RecallTargetKind, InvalidationAction, str],
    nonce: int,
) -> None:
    kind, action, terminal_state = case
    graph = synthetic_graph()
    factory = SqliteUnitOfWorkFactory(tmp_path / f"property-{kind.value}-{nonce}.sqlite3")
    factory.initialize()
    release_key, pack_key = _persist_graph(factory, graph)
    ActivationService(factory).activate(
        environment_id="property-environment",
        release=release_key,
        target_pack=pack_key,
        approval=approval(
            at=PREVIEW_AT - timedelta(minutes=30),
            rationale="Activate before dependency invalidation property testing.",
        ),
    )
    record = {
        RecallTargetKind.EVIDENCE: graph.evidence,
        RecallTargetKind.ARTIFACT: graph.artifact,
        RecallTargetKind.RELEASE: graph.release,
        RecallTargetKind.TARGET_PACK: graph.target_pack,
    }[kind]
    ledger = GovernanceLedger(Path(factory.path), subject_id="user-kevin")
    signer, _ = _recall_identity(ledger)
    service = RecallService(factory, subject_id="user-kevin")
    impact = service.preflight(
        impact_id=f"impact-property-{kind.value}-{nonce}",
        root_target=_target(kind, record),
        requested_action=action,
        generated_at=PREVIEW_AT,
        policy_version="1.0.0",
        signer=signer,
    )
    service.execute(
        impact_id=impact.impact_id,
        confirmation_digest=canonical_digest(impact),
        completed_at=COMPLETE_AT,
        reason="Every active dependent pointer must be atomically deactivated.",
        signer=signer,
    )

    with factory(write=False) as unit_of_work:
        current = unit_of_work.activations.current("property-environment")
        root_state = unit_of_work.lifecycle.current_state(
            RecordKey(kind.value, record.record_id, record.record_version)
        )
    assert current is not None and current.action == ActivationAction.DEACTIVATE.value
    assert root_state == terminal_state


def test_confirmed_purge_deletes_ciphertext_and_leaves_signed_tombstone(
    tmp_path: Path,
) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    raw_store = LocalRawPayloadStore(
        tmp_path / "raw",
        encryption_key=RawEncryptionKey(b"r" * 32),
    )
    raw_reference = raw_store.put(b"synthetic recall payload", media_type="text/plain")
    graph = synthetic_graph()
    evidence = graph.evidence.model_copy(
        update={
            "payload": PayloadReference(
                locator=raw_reference.relative_path,
                content_digest=f"sha256:{raw_reference.sha256}",
                media_type=raw_reference.media_type,
                byte_length=raw_reference.size_bytes,
            )
        }
    )
    task = graph.task.model_copy(update={"prompt_evidence_refs": (record_ref(evidence),)})
    DomainRecordStore(factory, subject_id="user-kevin").add_many((evidence, task))
    ledger = GovernanceLedger(Path(factory.path), subject_id="user-kevin")
    signer, _ = _recall_identity(ledger)
    impact = RecallService(factory, subject_id="user-kevin").preflight(
        impact_id="impact-purge",
        root_target=_target(RecallTargetKind.EVIDENCE, evidence),
        requested_action=InvalidationAction.PURGE_EVIDENCE,
        generated_at=PREVIEW_AT,
        policy_version="1.0.0",
        signer=signer,
    )
    assert len(impact.payloads) == 1

    with pytest.raises(RecallError, match="raw store and key"):
        RecallService(factory, subject_id="user-kevin").execute(
            impact_id=impact.impact_id,
            confirmation_digest=canonical_digest(impact),
            completed_at=COMPLETE_AT,
            reason="Missing keys must fail before any purge state commits.",
            signer=signer,
        )
    assert raw_store.contains(raw_reference)

    service = RecallService(factory, subject_id="user-kevin", raw_store=raw_store)
    report = service.execute(
        impact_id=impact.impact_id,
        confirmation_digest=canonical_digest(impact),
        completed_at=COMPLETE_AT,
        reason="Delete the selected encrypted payload after exact confirmation.",
        signer=signer,
    )

    assert not raw_store.contains(raw_reference)
    assert len(report.tombstone_refs) == 1
    assert report.purged_payload_digests == (f"sha256:{raw_reference.sha256}",)
    assert len(ledger.list(GovernanceObjectKind.TOMBSTONE_RECEIPT)) == 1
    with factory(write=False) as unit_of_work:
        state = unit_of_work.lifecycle.current_state(
            RecordKey("evidence", evidence.record_id, evidence.record_version)
        )
    assert state == "purged"


def test_consent_revocation_restricts_evidence_and_blocks_future_admission(
    tmp_path: Path,
) -> None:
    signer, identity = _identity()
    consent = _consent(signer)
    capture = _capture(signer, consent)
    evidence = _evidence(consent, capture)
    graph = synthetic_graph()
    task = graph.task.model_copy(
        update={
            "subject_id": "kevin",
            "scope": Scope(subject_ids=("kevin",)),
            "prompt_evidence_refs": (record_ref(evidence),),
        }
    )
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    ledger = GovernanceLedger(Path(factory.path), subject_id="kevin")
    ledger.add(identity)
    ledger.add(consent)
    ledger.add(capture)
    DomainRecordStore(factory, subject_id="kevin").add_many((evidence, task))
    service = RecallService(factory, subject_id="kevin")
    impact = service.preflight(
        impact_id="impact-consent-revocation",
        root_target=RecallTarget(
            target_kind=RecallTargetKind.CONSENT_RECEIPT,
            object_id=consent.receipt_id,
            content_digest=governance_ref(consent).content_digest,
        ),
        requested_action=InvalidationAction.REVOKE_CONSENT,
        generated_at=PREVIEW_AT,
        policy_version="1.0.0",
        signer=signer,
    )
    service.execute(
        impact_id=impact.impact_id,
        confirmation_digest=canonical_digest(impact),
        completed_at=COMPLETE_AT,
        reason="Withdraw consent for this exact source selector.",
        signer=signer,
    )
    invalidations = tuple(
        item
        for item in ledger.list(GovernanceObjectKind.INVALIDATION_EVENT)
        if isinstance(item, InvalidationEvent)
    )

    with pytest.raises(EvidenceGovernanceError, match="revoked"):
        validate_evidence_governance(
            evidence,
            consent=consent,
            capture=capture,
            identity=identity,
            invalidation_events=invalidations,
        )
    with factory(write=False) as unit_of_work:
        state = unit_of_work.lifecycle.current_state(
            RecordKey("evidence", evidence.record_id, evidence.record_version)
        )
    assert state == "restricted"
