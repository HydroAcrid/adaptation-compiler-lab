"""End-to-end synthetic ledger, raw-evidence, release, and activation persistence test."""

import json
from pathlib import Path

from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from adaptation_compiler_lab.persistence.records import (
    ActivationEvent,
    LifecycleEvent,
    RecordKey,
    RecordLink,
    StoredRecord,
    sha256_text,
)
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

STAMP = "2026-07-22T12:00:00+00:00"


def canonical(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def make_record(kind: str, record_id: str, *, value: str = "fixture") -> StoredRecord:
    payload = canonical({"id": record_id, "kind": kind, "value": value, "version": "1"})
    return StoredRecord(
        key=RecordKey(kind, record_id, "1"),
        schema_version="1.0",
        canonicalization_version="1",
        canonical_json=payload,
        content_sha256=sha256_text(payload),
        created_at=STAMP,
        subject_id="subject-kevin",
        privacy_class="internal",
        benchmark_role="construction",
    )


def make_lifecycle(event_id: str, entity: RecordKey, to_state: str) -> LifecycleEvent:
    payload = canonical(
        {
            "entity": [entity.kind, entity.record_id, entity.version],
            "event_id": event_id,
            "to": to_state,
        }
    )
    return LifecycleEvent(
        event_id=event_id,
        entity=entity,
        from_state=None,
        to_state=to_state,
        previous_event_id=None,
        actor_id="reviewer-1",
        policy_version="1",
        reason="synthetic transition",
        occurred_at=STAMP,
        canonical_json=payload,
        event_sha256=sha256_text(payload),
    )


def make_activation(
    event_id: str,
    action: str,
    *,
    release: RecordKey,
    target_pack: RecordKey,
) -> ActivationEvent:
    payload = canonical(
        {
            "action": action,
            "event_id": event_id,
            "release": [release.kind, release.record_id, release.version],
            "target_pack": [target_pack.kind, target_pack.record_id, target_pack.version],
        }
    )
    return ActivationEvent(
        event_id=event_id,
        environment_id="local-dev",
        action=action,
        release=release,
        target_pack=target_pack,
        previous_event_id=None,
        actor_id="operator-1",
        reason="synthetic activation",
        occurred_at=STAMP,
        canonical_json=payload,
        event_sha256=sha256_text(payload),
    )


def test_synthetic_release_graph_survives_reopen_without_raw_payload_leakage(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ledger" / "ledger.sqlite3"
    raw_store = LocalRawPayloadStore(tmp_path / "raw-evidence")
    secret = b"synthetic-secret-that-must-not-enter-ledger"
    raw_reference = raw_store.put(secret, media_type="text/plain")

    task = make_record("task_record", "task-1")
    evidence_payload = canonical(
        {
            "id": "evidence-1",
            "payload_ref": {
                "media_type": raw_reference.media_type,
                "relative_path": raw_reference.relative_path,
                "sha256": raw_reference.sha256,
                "size_bytes": raw_reference.size_bytes,
            },
            "source_class": "explicit_user_feedback",
        }
    )
    evidence = StoredRecord(
        key=make_record("evidence", "evidence-1").key,
        schema_version="1.0",
        canonicalization_version="1",
        canonical_json=evidence_payload,
        content_sha256=sha256_text(evidence_payload),
        created_at=STAMP,
        subject_id="subject-kevin",
        privacy_class="restricted",
        benchmark_role="construction",
    )
    artifact = make_record("artifact", "artifact-1", value="abstract behavior only")
    release = make_record("release", "release-1")
    target_pack = make_record("target_pack", "pack-1", value="rendered abstract behavior")

    factory = SqliteUnitOfWorkFactory(database_path)
    factory.initialize()
    with factory() as unit_of_work:
        for record in (task, evidence, artifact, release, target_pack):
            unit_of_work.records.add(record)
        unit_of_work.links.add(RecordLink(evidence.key, task.key, "observed_in", 0, STAMP))
        unit_of_work.links.add(RecordLink(artifact.key, evidence.key, "supports", 0, STAMP))
        unit_of_work.links.add(RecordLink(release.key, artifact.key, "contains_artifact", 0, STAMP))
        unit_of_work.links.add(RecordLink(target_pack.key, release.key, "rendered_from", 0, STAMP))
        unit_of_work.lifecycle.append(make_lifecycle("release-frozen", release.key, "released"))
        unit_of_work.lifecycle.append(
            make_lifecycle("pack-validated", target_pack.key, "validated")
        )
        activation = make_activation(
            "activate-pack",
            "activate",
            release=release.key,
            target_pack=target_pack.key,
        )
        unit_of_work.activations.append(activation, expected_previous_event_id=None)
        unit_of_work.commit()

    reopened = SqliteUnitOfWorkFactory(database_path)
    reopened.initialize()
    with reopened(write=False) as unit_of_work:
        assert unit_of_work.records.require(evidence.key) == evidence
        assert unit_of_work.links.incoming(evidence.key) == (
            RecordLink(artifact.key, evidence.key, "supports", 0, STAMP),
        )
        assert unit_of_work.activations.current("local-dev") == activation
        assert raw_reference.relative_path not in target_pack.canonical_json

    assert secret not in database_path.read_bytes()
    assert raw_store.read(raw_reference) == secret
