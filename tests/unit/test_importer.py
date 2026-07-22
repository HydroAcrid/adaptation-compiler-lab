from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.application.importer import BundleImportError, import_task_bundle
from adaptation_compiler_lab.application.record_store import DomainRecordStore
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
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory


def _evidence(text: str) -> Evidence:
    encoded = text.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    actor = ActorRef(actor_id="fixture-system", kind=ActorKind.SYSTEM, version="1.0.0")
    return Evidence(
        record_id="evidence-import-1",
        record_version="1.0.0",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_by=actor,
        policy_version="1.0.0",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        producer=actor,
        source_class=SourceClass.SYNTHETIC,
        authority_class=AuthorityClass.SYNTHETIC_ONLY,
        authority_reason="Synthetic fixture authority only.",
        allowed_claim_types=(ClaimType.SYNTHETIC_EXPECTATION,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator=f"sha256/{digest[:2]}/{digest}",
            content_digest=f"sha256:{digest}",
            media_type="text/plain",
            byte_length=len(encoded),
        ),
        synthetic_origin=SyntheticOrigin(
            fixture_id="fixture-import",
            description="Synthetic manual import fixture.",
        ),
        scope=Scope(subject_ids=("synthetic-user",)),
        privacy=PrivacyContext(
            sensitivity=SensitivityClass.INTERNAL,
            consent_basis="synthetic-fixture",
            permitted_uses=(PermittedUse.CONSTRUCTION,),
        ),
        partition=Partition.SYNTHETIC,
    )


def _write_bundle(path: Path, evidence: Evidence, text: str) -> None:
    path.write_text(
        json.dumps(
            {
                "bundle_version": "1.0",
                "subject_id": "synthetic-user",
                "records": [evidence.model_dump(mode="json")],
                "raw_payloads": [
                    {
                        "evidence_record_id": evidence.record_id,
                        "evidence_record_version": evidence.record_version,
                        "media_type": "text/plain",
                        "source_path": "synthetic/input.txt",
                        "text": text,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _services(tmp_path: Path) -> tuple[DomainRecordStore, LocalRawPayloadStore]:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    return (
        DomainRecordStore(factory, subject_id="synthetic-user"),
        LocalRawPayloadStore(
            tmp_path / "raw-evidence",
            encryption_key=RawEncryptionKey(b"r" * 32),
        ),
    )


def test_safe_synthetic_bundle_imports_metadata_and_segregated_raw_bytes(tmp_path: Path) -> None:
    text = "Synthetic correction payload with no credentials."
    evidence = _evidence(text)
    bundle_path = tmp_path / "bundle.json"
    _write_bundle(bundle_path, evidence, text)
    record_store, raw_store = _services(tmp_path)

    result = import_task_bundle(
        bundle_path,
        expected_subject_id="synthetic-user",
        record_store=record_store,
        raw_store=raw_store,
    )

    assert result.imported_record_keys == ("evidence:evidence-import-1@1.0.0",)
    assert len(record_store.list(record_kind="evidence")) == 1
    assert (
        raw_store.read(raw_store.reference_for(text.encode(), media_type="text/plain"))
        == text.encode()
    )


def test_secret_like_payload_is_rejected_before_raw_storage(tmp_path: Path) -> None:
    text = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    evidence = _evidence(text)
    bundle_path = tmp_path / "bundle.json"
    _write_bundle(bundle_path, evidence, text)
    record_store, raw_store = _services(tmp_path)

    with pytest.raises(BundleImportError, match="provider_token"):
        import_task_bundle(
            bundle_path,
            expected_subject_id="synthetic-user",
            record_store=record_store,
            raw_store=raw_store,
        )

    assert not list((raw_store.root / "sha256").glob("**/*"))
    assert record_store.list() == ()


def test_sensitive_bundle_filename_variants_are_rejected(tmp_path: Path) -> None:
    text = "Synthetic payload."
    evidence = _evidence(text)
    bundle_path = tmp_path / ".env.local"
    _write_bundle(bundle_path, evidence, text)
    record_store, raw_store = _services(tmp_path)

    with pytest.raises(BundleImportError, match="sensitive-path"):
        import_task_bundle(
            bundle_path,
            expected_subject_id="synthetic-user",
            record_store=record_store,
            raw_store=raw_store,
        )


def test_failed_record_transaction_discards_new_raw_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = "Synthetic payload written before a simulated ledger failure."
    evidence = _evidence(text)
    bundle_path = tmp_path / "bundle.json"
    _write_bundle(bundle_path, evidence, text)
    record_store, raw_store = _services(tmp_path)

    def fail_persistence(records: object) -> object:
        del records
        raise ValueError("simulated transaction failure")

    monkeypatch.setattr(record_store, "add_many", fail_persistence)

    with pytest.raises(BundleImportError, match="simulated transaction failure"):
        import_task_bundle(
            bundle_path,
            expected_subject_id="synthetic-user",
            record_store=record_store,
            raw_store=raw_store,
        )

    assert not list((raw_store.root / "sha256").glob("**/*"))
