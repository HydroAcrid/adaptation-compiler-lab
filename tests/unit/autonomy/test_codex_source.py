from __future__ import annotations

import base64
import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import codex_dogfood_schemas
from adaptation_compiler_lab.autonomy.codex_source import (
    CodexHabitSource,
    HabitSourceCursorV1,
    StoredOriginEvidence,
)
from adaptation_compiler_lab.autonomy.models import InputOrigin, StyleCategory
from adaptation_compiler_lab.autonomy.origin_receipts import (
    AdmittedOriginProducerV1,
    OriginReceiptV1,
)
from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import (
    load_dogfood_runtime_pins,
    product_codex_runtime_locks,
)
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.serialization import canonical_digest

NOW = datetime(2026, 10, 14, 15, tzinfo=UTC)
BINDING = "sha256:" + "a" * 64
VERSION = "0.162.0-alpha.17.2"


@dataclass
class ReadOnlyRpc:
    thread: dict[str, Any]
    calls: list[str] = field(default_factory=list)

    def request(self, method: str, params: JsonObject) -> JsonObject:
        self.calls.append(method)
        if method == "thread/list":
            summary = {**self.thread, "turns": []}
            return cast(JsonObject, {"data": [summary], "nextCursor": None})
        if method == "thread/read":
            return cast(JsonObject, {"thread": deepcopy(self.thread)})
        raise AssertionError("source attempted a non-reader operation")


@pytest.fixture
def fixture(tmp_path: Path) -> dict[str, Any]:
    pin = next(
        load_dogfood_runtime_pins(path).codex
        for path in product_codex_runtime_locks("win32")
        if load_dogfood_runtime_pins(path).codex.executable.package_version == VERSION
    )
    home = tmp_path / "codex"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    store = AutonomyStore(
        tmp_path / "private/events.sqlite3",
        signer=GovernanceSigner(Ed25519PrivateKey.generate(), "owner", "subject"),
        raw_store=LocalRawPayloadStore(
            tmp_path / "private/raw", encryption_key=RawEncryptionKey(b"k" * 32)
        ),
    )
    service = AutonomyApplicationService(
        store=store,
        projects={"project": project},
        codex_home=home,
        clock=lambda: NOW - timedelta(hours=3),
    )
    preview = service.preview_grant(("project",), (StyleCategory.COMMUNICATION_DETAIL,))
    service.confirm_grant(preview["preview_token"], confirmed=True, idempotency_key="grant")
    grant = service.grant()
    assert grant is not None
    service.clock = lambda: NOW
    evidence = StoredOriginEvidence(
        store, client_version=VERSION, binary_digest=pin.executable.executable_sha256
    )
    producer_signer = GovernanceSigner(Ed25519PrivateKey.generate(), "input-producer", "subject")
    producer = AdmittedOriginProducerV1(
        producer_id="fictional-input-producer",
        source_client="codex-interactive",
        client_version=VERSION,
        client_binary_digest=pin.executable.executable_sha256,
        public_key_base64=base64.b64encode(
            producer_signer.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode(),
        human_fixture_passed=True,
        automated_fixture_passed=True,
        project_ids=("project",),
    )
    # Test-only owner admission. These fictional fixtures do not admit a native producer.
    store.append(
        "fictional-admission",
        "origin_producer_admitted",
        {"grant_digest": grant.content_digest, "producer": producer.model_dump(mode="json")},
        at=NOW,
    )
    text = "Could you shorten the progress update?"
    thread = {
        "id": "fictional-chat",
        "sessionId": "fictional-session",
        "source": "appServer",
        "modelProvider": "openai",
        "projectId": None,
        "preview": "private preview",
        "createdAt": int((NOW - timedelta(hours=2)).timestamp()),
        "updatedAt": int((NOW - timedelta(hours=1)).timestamp()),
        "status": {"type": "idle"},
        "cwd": str(project),
        "cliVersion": VERSION,
        "ephemeral": False,
        "turns": [
            {
                "id": "fictional-turn",
                "status": "completed",
                "completedAt": int((NOW - timedelta(hours=1)).timestamp()),
                "items": [
                    {
                        "type": "userMessage",
                        "id": "fictional-message",
                        "clientId": None,
                        "content": [{"type": "text", "text": text, "text_elements": []}],
                    }
                ],
            }
        ],
    }
    rpc = ReadOnlyRpc(thread)
    source = CodexHabitSource(
        rpc,
        schemas=codex_dogfood_schemas(pin),
        projects={"project": (project,)},
        grant=grant,
        evidence=evidence,
        source_binding=BINDING,
        clock=lambda: NOW,
    )
    return locals()


def receipt(
    f: dict[str, Any], *, origin: InputOrigin = InputOrigin.HUMAN, text: str | None = None
) -> None:
    payload = {
        "receipt_version": "1.0.0",
        "producer_id": f["producer"].producer_id,
        "source_client": "codex-interactive",
        "client_version": VERSION,
        "client_binary_digest": f["pin"].executable.executable_sha256,
        "project_id": "project",
        "task_id": "fictional-chat",
        "message_id": "fictional-message",
        "text_digest": canonical_digest({"text": f["text"] if text is None else text}),
        "origin": origin,
        "observed_at": (NOW - timedelta(minutes=90)).isoformat(),
    }
    value = OriginReceiptV1.model_validate_json(
        json.dumps(
            {
                **payload,
                "signature": f["producer_signer"]
                .envelope(payload, purpose="temper_input_origin", signed_at=NOW)
                .model_dump(mode="json"),
            }
        )
    )
    value = value.model_copy(
        update={
            "signature": f["producer_signer"].envelope(
                value.unsigned, purpose="temper_input_origin", signed_at=NOW
            )
        }
    )
    f["store"].append(
        "fictional-origin", "input_origin_receipt", value.model_dump(mode="json"), at=NOW
    )


def test_native_schema_completed_chat_enters_encrypted_shadow_lane_once(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    receipt(f)
    page = f["source"].poll(f["grant"].issued_at, None)
    assert len(page.episodes) == 1
    episode = page.episodes[0]
    assert f["evidence"].verify_episode(episode, f["grant"])
    f["service"].provenance_verifier = lambda value: f["evidence"].verify_episode(value, f["grant"])
    assert f["service"].ingest_episode(episode)
    assert not f["service"].ingest_episode(episode)
    assert f["source"].poll(f["grant"].issued_at, page.cursor).episodes == ()
    assert f["rpc"].calls == ["thread/list", "thread/read"] * 2
    assert f["text"] not in page.cursor
    assert f["text"] not in f["store"].path.read_bytes().decode(errors="replace")


@pytest.mark.parametrize(
    "origin",
    [None, InputOrigin.AGENT, InputOrigin.DELEGATED, InputOrigin.COPIED, InputOrigin.UNKNOWN],
)
def test_unverified_automated_or_copied_input_never_becomes_evidence(
    fixture: dict[str, Any], origin: InputOrigin | None
) -> None:
    f = fixture
    if origin is not None:
        receipt(f, origin=origin)
    page = f["source"].poll(f["grant"].issued_at, None)
    assert not page.episodes
    assert not HabitSourceCursorV1.model_validate_json(page.cursor).checkpoints
    assert not any(event["type"] == "source_episode_proof" for event in f["store"].events())
    assert not list(f["store"].raw_store.root.rglob("*.raw"))


@pytest.mark.parametrize(
    "change",
    [
        {"createdAt": int((NOW - timedelta(days=1)).timestamp())},
        {"cwd": "/unrelated/project"},
        {"status": {"type": "active", "activeFlags": []}},
        {"ephemeral": True},
        {"cliVersion": "unsupported"},
        {"forkedFromId": "old-chat"},
        {"parentThreadId": "parent-agent"},
        {"source": "exec"},
        {"updatedAt": int((NOW - timedelta(minutes=2)).timestamp())},
    ],
)
def test_ineligible_chats_are_excluded_before_read(
    fixture: dict[str, Any], change: dict[str, Any]
) -> None:
    f = fixture
    f["thread"].update(change)
    assert not f["source"].poll(f["grant"].issued_at, None).episodes
    assert f["rpc"].calls == ["thread/list"]


def test_receipt_binds_exact_text_and_revocation_invalidates_proof(fixture: dict[str, Any]) -> None:
    f = fixture
    receipt(f)
    page = f["source"].poll(f["grant"].issued_at, None)
    episode = page.episodes[0]
    assert not f["evidence"].verify_episode(
        episode.model_copy(update={"text": "Different"}), f["grant"]
    )
    f["store"].append(
        "revoke-origin",
        "origin_producer_revoked",
        {"producer_id": f["producer"].producer_id},
        at=NOW,
    )
    assert not f["evidence"].verify_episode(episode, f["grant"])
    f["rpc"].calls.clear()
    with pytest.raises(AutonomyIntegrityError, match="not admitted"):
        f["source"].poll(f["grant"].issued_at, page.cursor)
    assert not f["rpc"].calls


def test_cursor_binding_and_edited_history_require_attention(fixture: dict[str, Any]) -> None:
    f = fixture
    receipt(f)
    page = f["source"].poll(f["grant"].issued_at, None)
    cursor = HabitSourceCursorV1.model_validate_json(page.cursor)
    bad = cursor.model_copy(update={"source_binding": "sha256:" + "b" * 64})
    with pytest.raises(AutonomyIntegrityError, match="another grant or native source"):
        f["source"].poll(f["grant"].issued_at, bad.model_dump_json())
    f["thread"]["turns"][0]["items"][0]["content"][0]["text"] = "Edited after pickup"
    with pytest.raises(AutonomyIntegrityError, match="prefix changed"):
        f["source"].poll(f["grant"].issued_at, page.cursor)


def test_missing_native_admission_and_wrong_receipt_refuse_capture(fixture: dict[str, Any]) -> None:
    f = fixture
    receipt(f, text="Another prompt")
    assert not f["source"].poll(f["grant"].issued_at, None).episodes
    assert not f["evidence"].producers(f["grant"].model_copy(update={"grant_id": "another-grant"}))


@pytest.mark.parametrize("completed", [None, int((NOW - timedelta(minutes=2)).timestamp())])
def test_metadata_updates_cannot_supply_a_missing_or_recent_completion_date(
    fixture: dict[str, Any], completed: int | None
) -> None:
    f = fixture
    receipt(f)
    f["thread"]["turns"][0]["completedAt"] = completed
    assert not f["source"].poll(f["grant"].issued_at, None).episodes


def test_resumed_conversation_cannot_manufacture_another_supporting_task(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    receipt(f)
    page = f["source"].poll(f["grant"].issued_at, None)
    another = deepcopy(f["thread"]["turns"][0])
    another["id"] = "another-turn"
    another["items"][0]["id"] = "another-message"
    f["thread"]["turns"].append(another)
    assert not f["source"].poll(f["grant"].issued_at, page.cursor).episodes


def test_new_producer_key_does_not_revalidate_revoked_old_evidence(fixture: dict[str, Any]) -> None:
    f = fixture
    receipt(f)
    page = f["source"].poll(f["grant"].issued_at, None)
    f["store"].append(
        "revoke-old-key",
        "origin_producer_revoked",
        {"producer_id": f["producer"].producer_id},
        at=NOW,
    )
    replacement = f["producer"].model_copy(
        update={
            "public_key_base64": base64.b64encode(
                Ed25519PrivateKey.generate()
                .public_key()
                .public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode()
        }
    )
    f["store"].append(
        "admit-replacement",
        "origin_producer_admitted",
        {
            "grant_digest": f["grant"].content_digest,
            "producer": replacement.model_dump(mode="json"),
        },
        at=NOW,
    )
    assert not f["evidence"].verify_episode(page.episodes[0], f["grant"])


def test_revocation_closes_an_already_running_worker_before_any_source_read(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    service = f["service"]
    service.provenance_verifier = lambda value: f["evidence"].verify_episode(value, service.grant())
    service.provenance_admission = lambda: bool(f["evidence"].producers(f["grant"]))
    worker = BackgroundHabitWorker(service, read_completed=f["source"].poll)
    assert service.status()["provenance_state"] == "verified"
    f["store"].append(
        "revoke-live-producer",
        "origin_producer_revoked",
        {"producer_id": f["producer"].producer_id},
        at=NOW,
    )
    assert service.status()["provenance_state"] == "unverified"
    assert not service.automatic_ready()
    assert worker.poll()["status"] == "source_verification_required"
    assert f["rpc"].calls == []


def test_completed_reader_integrates_with_existing_worker_without_second_capture_lane(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    receipt(f)
    service = f["service"]
    service.provenance_verifier = lambda value: f["evidence"].verify_episode(value, service.grant())
    service.provenance_admission = lambda: bool(f["evidence"].producers(f["grant"]))
    worker = BackgroundHabitWorker(service, read_completed=f["source"].poll)
    result = worker.poll()
    assert result["captured"] == 1
    assert result["analyzed"] == 0
    assert result["status"] == "analysis_verification_required"
    assert len(service.episodes()) == 1
    assert not service.status()["personalization_enabled"]
    assert f["store"].latest("cursor") is not None
