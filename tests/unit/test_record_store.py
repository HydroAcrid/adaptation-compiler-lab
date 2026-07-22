from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from adaptation_compiler_lab.application.record_store import DomainRecordStore, DomainStoreError
from adaptation_compiler_lab.domain.base import ActorRef
from adaptation_compiler_lab.domain.enums import (
    ActorKind,
    AuthorityClass,
    ClaimType,
    EvidenceState,
    Partition,
    PermittedUse,
    RedactionState,
    SensitivityClass,
    SourceClass,
)
from adaptation_compiler_lab.domain.records import Evidence
from adaptation_compiler_lab.domain.values import (
    PayloadReference,
    PrivacyContext,
    Scope,
    SyntheticOrigin,
)
from adaptation_compiler_lab.persistence.ports import UnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import RecordKey, StoredRecord
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

NOW = datetime(2026, 1, 1, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


class _CorruptReadRepository:
    """Deliberately untrusted storage port used to exercise read-boundary validation."""

    def __init__(self, record: StoredRecord) -> None:
        self._record = record

    def get(self, key: RecordKey) -> StoredRecord | None:
        del key
        return self._record

    def list_records(self, **_: object) -> tuple[StoredRecord, ...]:
        return (self._record,)


class _CorruptReadUnitOfWork:
    def __init__(self, record: StoredRecord) -> None:
        self.records = _CorruptReadRepository(record)

    def __enter__(self) -> _CorruptReadUnitOfWork:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _CorruptReadFactory:
    def __init__(self, record: StoredRecord) -> None:
        self._unit_of_work = _CorruptReadUnitOfWork(record)

    def __call__(self, *, write: bool = True) -> _CorruptReadUnitOfWork:
        if write:
            raise AssertionError("corrupt read fixture must not receive a write request")
        return self._unit_of_work


def corrupt_read_store(record: StoredRecord) -> DomainRecordStore:
    factory = cast(UnitOfWorkFactory, _CorruptReadFactory(record))
    return DomainRecordStore(factory, subject_id="synthetic-user")


def synthetic_evidence(*, subject_id: str = "synthetic-user") -> Evidence:
    actor = ActorRef(actor_id="fixture-system", kind=ActorKind.SYSTEM, version="1.0.0")
    return Evidence(
        record_id="evidence-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=actor,
        policy_version="1.0.0",
        observed_at=NOW,
        producer=actor,
        source_class=SourceClass.SYNTHETIC,
        authority_class=AuthorityClass.SYNTHETIC_ONLY,
        authority_reason="Synthetic fixture authority only.",
        allowed_claim_types=(ClaimType.SYNTHETIC_EXPECTATION,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator="raw-evidence/sha256/aa/" + "a" * 64,
            content_digest=DIGEST,
            media_type="text/plain",
            byte_length=8,
        ),
        synthetic_origin=SyntheticOrigin(
            fixture_id="fixture-1",
            description="Synthetic storage adapter fixture.",
        ),
        scope=Scope(subject_ids=(subject_id,)),
        privacy=PrivacyContext(
            sensitivity=SensitivityClass.INTERNAL,
            consent_basis="synthetic-fixture",
            permitted_uses=(PermittedUse.CONSTRUCTION,),
        ),
        partition=Partition.SYNTHETIC,
    )


def test_domain_record_round_trip(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    store = DomainRecordStore(factory, subject_id="synthetic-user")
    evidence = synthetic_evidence()

    key = store.add(evidence)
    loaded = store.require(key)

    assert loaded.record == evidence
    assert loaded.key == key
    assert store.list(record_kind="evidence") == (loaded,)


def test_workspace_subject_is_enforced(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    store = DomainRecordStore(factory, subject_id="different-subject")

    with pytest.raises(DomainStoreError, match="only the workspace subject"):
        store.add(synthetic_evidence())


def test_workspace_rejects_shared_subject_scope(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    store = DomainRecordStore(factory, subject_id="synthetic-user")
    shared_scope = Scope(subject_ids=("another-user", "synthetic-user"))
    evidence = synthetic_evidence().model_copy(update={"scope": shared_scope})

    with pytest.raises(DomainStoreError, match="only the workspace subject"):
        store.add(evidence)


def test_other_subject_record_is_not_disclosed(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    owner = DomainRecordStore(factory, subject_id="synthetic-user")
    other_subject = DomainRecordStore(factory, subject_id="another-user")
    key = owner.add(synthetic_evidence())

    assert other_subject.get(key) is None
    with pytest.raises(DomainStoreError, match="not found"):
        other_subject.require(key)
    assert other_subject.list() == ()


def test_read_paths_reject_tampered_canonicalization_metadata(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    key = DomainRecordStore(factory, subject_id="synthetic-user").add(synthetic_evidence())
    with factory(write=False) as unit_of_work:
        stored = unit_of_work.records.require(key)
    store = corrupt_read_store(replace(stored, canonicalization_version="999.0.0"))

    with pytest.raises(DomainStoreError, match="canonicalization version"):
        store.get(key)
    with pytest.raises(DomainStoreError, match="canonicalization version"):
        store.require(key)
    with pytest.raises(DomainStoreError, match="canonicalization version"):
        store.list()


def test_list_rejects_tampered_stored_key_kind(tmp_path: Path) -> None:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    key = DomainRecordStore(factory, subject_id="synthetic-user").add(synthetic_evidence())
    with factory(write=False) as unit_of_work:
        stored = unit_of_work.records.require(key)
    store = corrupt_read_store(replace(stored, key=replace(stored.key, kind="unknown_kind")))

    with pytest.raises(DomainStoreError, match="supported domain record kind"):
        store.list()
