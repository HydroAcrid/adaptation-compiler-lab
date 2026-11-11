from __future__ import annotations

import os
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.capture_policy import (
    CapturePolicyController,
    completed_work_authorization,
)
from adaptation_compiler_lab.autonomy.models import InputOrigin
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from tests.unit.autonomy.test_authorized_chats import authorize
from tests.unit.autonomy.test_codex_source import NOW
from tests.unit.autonomy.test_codex_source import fixture as fixture


def enable_work(
    f: dict[str, Any], bindings: list[dict[str, str]] | None = None
) -> CapturePolicyController:
    authorize(f)
    f["thread"]["turns"][0]["startedAt"] = int((NOW - timedelta(minutes=90)).timestamp())
    controller = CapturePolicyController(f["service"])
    preview = controller.preview(bindings or [])
    controller.enable(preview["preview_token"], confirmed=True, key="enable-work")
    f["source"].completed_work = completed_work_authorization(f["store"], f["grant"])
    return controller


@pytest.mark.parametrize("last_status", ["interrupted", "inProgress"])
def test_actual_ongoing_chat_shape_captures_only_new_completed_work_once(
    fixture: dict[str, Any], last_status: str
) -> None:
    f = fixture
    (f["project"] / ".git").mkdir()
    collection = f["project"].parent
    bindings = [{"thread_id": "fictional-chat", "project_id": "project", "cwd": str(collection)}]
    enable_work(f, bindings)
    thread = f["thread"]
    thread.update(
        createdAt=int((NOW - timedelta(days=7)).timestamp()),
        updatedAt=int((NOW - timedelta(minutes=1)).timestamp()),
        cliVersion="0.160.1",
        cwd=str(collection),
        status={"type": "active", "activeFlags": []},
    )
    old = deepcopy(thread["turns"][0])
    old.update(
        id="old-turn",
        startedAt=int((NOW - timedelta(days=7)).timestamp()),
        completedAt=int((NOW - timedelta(days=7) + timedelta(minutes=1)).timestamp()),
    )
    old["items"][0].update(id="old-message")
    old["items"][0]["content"][0]["text"] = "Old content must stay outside learning."
    unfinished = deepcopy(thread["turns"][0])
    unfinished.update(
        id="latest-turn",
        status=last_status,
        startedAt=int((NOW - timedelta(minutes=2)).timestamp()),
        completedAt=None,
    )
    unfinished["items"][0].update(id="unfinished-message")
    unfinished["items"][0]["content"][0]["text"] = "Unfinished content must stay outside learning."
    thread["turns"] = [old, thread["turns"][0], unfinished]
    page = f["source"].poll(f["grant"].issued_at, None)
    assert len(page.episodes) == 1, "new completed work was rejected by immutable thread metadata"
    episode = page.episodes[0]
    assert episode.text == f["text"], "pre-cutoff or unfinished work entered live capture"
    assert episode.observation_ids == ("fictional-message",)
    assert episode.created_at == NOW - timedelta(minutes=90)
    assert episode.origin is InputOrigin.AUTHORIZED_CHAT
    assert f["evidence"].verify_episode(episode, f["grant"])
    assert f["service"].ingest_episode(episode)
    assert not f["source"].poll(f["grant"].issued_at, page.cursor).episodes
    assert (
        "Old content"
        not in f["service"]
        .store.raw(f["service"].episodes()[episode.episode_id]["raw_ref"])
        .decode()
    )


def test_owner_policy_preserves_grant_history_and_does_not_reauthorize_categories(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    authorize(f)
    before = f["grant"].model_dump_json()
    head = f["store"].head_digest
    controller = CapturePolicyController(f["service"])
    preview = controller.preview([])
    assert f["store"].head_digest == head
    assert preview["historical_messages_before_cutoff"] is False
    assert completed_work_authorization(f["store"], f["grant"]) is None
    with pytest.raises(AutonomyIntegrityError, match="confirmation"):
        controller.enable(preview["preview_token"], confirmed=False, key="not-approved")
    controller.enable(preview["preview_token"], confirmed=True, key="approved")
    controller.enable(preview["preview_token"], confirmed=True, key="approved")
    assert f["service"].grant().model_dump_json() == before
    assert len([e for e in f["store"].events() if e["type"] == "source_work_authorization"]) == 1
    controller.disable(key="stop-window")
    assert completed_work_authorization(f["store"], f["grant"]) is None


@pytest.mark.parametrize("failure", ["changed_head", "locked_store", "expired_preview"])
def test_changed_or_unavailable_owner_context_cannot_enable_work(
    fixture: dict[str, Any],
    failure: str,
) -> None:
    f = fixture
    authorize(f)
    controller = CapturePolicyController(f["service"])
    preview = controller.preview([])
    if failure == "changed_head":
        f["store"].append("other", "diagnostic", {}, at=NOW)
    elif failure == "locked_store":
        f["service"].secure_store_available = lambda: False
    else:
        f["service"].clock = lambda: NOW + timedelta(minutes=16)
    with pytest.raises(AutonomyIntegrityError):
        controller.enable(preview["preview_token"], confirmed=True, key="stale")
    assert completed_work_authorization(f["store"], f["grant"]) is None


@pytest.mark.parametrize(
    "change",
    [
        {"startedAt": None},
        {"startedAt": int((NOW - timedelta(days=1)).timestamp())},
        {"completedAt": None},
        {"status": "failed"},
        {"completedAt": int((NOW - timedelta(minutes=2)).timestamp())},
    ],
)
def test_missing_old_failed_or_recent_turns_do_not_enter_the_window(
    fixture: dict[str, Any],
    change: dict[str, Any],
) -> None:
    f = fixture
    enable_work(f)
    f["thread"]["turns"][0].update(change)
    assert not f["source"].poll(f["grant"].issued_at, None).episodes


def test_later_project_cutoff_still_limits_completed_work(fixture: dict[str, Any]) -> None:
    f = fixture
    enable_work(f)
    f["source"].project_cutoffs = {"project": NOW - timedelta(minutes=80)}
    assert not f["source"].poll(f["grant"].issued_at, None).episodes


def test_old_chat_inside_registered_repo_needs_no_collection_binding(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    enable_work(f)
    f["thread"]["createdAt"] = int((NOW - timedelta(days=7)).timestamp())
    page = f["source"].poll(f["grant"].issued_at, None)
    assert len(page.episodes) == 1
    assert page.episodes[0].text == f["text"]


def test_recent_completion_cannot_import_turns_older_than_retention(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    enable_work(f)
    later = NOW + timedelta(days=31)
    f["source"].clock = lambda: later
    f["thread"]["updatedAt"] = int((later - timedelta(minutes=60)).timestamp())
    fresh = deepcopy(f["thread"]["turns"][0])
    fresh.update(
        id="fresh-turn",
        startedAt=int((later - timedelta(minutes=90)).timestamp()),
        completedAt=int((later - timedelta(minutes=60)).timestamp()),
    )
    fresh["items"][0].update(id="fresh-message")
    fresh["items"][0]["content"][0]["text"] = "Only recent work belongs in this episode."
    f["thread"]["turns"].append(fresh)
    page = f["source"].poll(f["grant"].issued_at, None)
    assert len(page.episodes) == 1
    assert page.episodes[0].text == "Only recent work belongs in this episode."
    assert page.episodes[0].observation_ids == ("fresh-message",)


def test_resumed_captured_chat_stays_one_episode_after_checkpoint_expiry(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    enable_work(f)
    first = f["source"].poll(f["grant"].issued_at, None)
    assert f["service"].ingest_episode(first.episodes[0])
    later = NOW + timedelta(days=31)
    f["source"].clock = lambda: later
    f["thread"]["updatedAt"] = int((later - timedelta(minutes=60)).timestamp())
    resumed = deepcopy(f["thread"]["turns"][0])
    resumed.update(
        id="resumed-turn",
        startedAt=int((later - timedelta(minutes=90)).timestamp()),
        completedAt=int((later - timedelta(minutes=60)).timestamp()),
    )
    resumed["items"][0]["id"] = "resumed-message"
    f["thread"]["turns"].append(resumed)
    second = f["source"].poll(f["grant"].issued_at, first.cursor)
    assert not second.episodes, "checkpoint expiry manufactured a second conversation episode"
    assert len(f["service"].episodes()) == 1


def test_exact_conversation_binding_does_not_authorize_its_parent_folder(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    (f["project"] / ".git").mkdir()
    collection = f["project"].parent
    enable_work(
        f, [{"thread_id": "fictional-chat", "project_id": "project", "cwd": str(collection)}]
    )
    f["thread"].update(cwd=str(collection), id="another-chat")
    assert not f["source"].poll(f["grant"].issued_at, None).episodes
    f["thread"].update(id="fictional-chat", cwd=str(f["project"]))
    with pytest.raises(AutonomyIntegrityError, match="moved"):
        f["source"].poll(f["grant"].issued_at, None)


@pytest.mark.skipif(os.name != "nt", reason="Windows extended path spelling")
def test_bound_chat_accepts_another_spelling_of_its_directory(
    fixture: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fixture
    (f["project"] / ".git").mkdir()
    collection = f["project"].parent
    enable_work(
        f, [{"thread_id": "fictional-chat", "project_id": "project", "cwd": str(collection)}]
    )
    alias = Path("\\\\?\\" + str(collection))
    assert alias != collection and alias.samefile(collection)
    f["thread"]["cwd"] = str(alias)
    # WSL can retain the extended path spelling after the native resolver.
    monkeypatch.setattr(
        "adaptation_compiler_lab.autonomy.codex_source._resolved_runtime_path", Path
    )
    page = f["source"].poll(f["grant"].issued_at, None)
    assert [episode.project_id for episode in page.episodes] == ["project"]


def test_disabled_or_other_grant_cannot_reuse_source_permission(fixture: dict[str, Any]) -> None:
    f = fixture
    enable_work(f)
    assert completed_work_authorization(f["store"], f["grant"]) is not None
    assert (
        completed_work_authorization(
            f["store"], f["grant"].model_copy(update={"grant_id": "other"})
        )
        is None
    )
    f["service"].revoke_grant(key="revoke")
    assert completed_work_authorization(f["store"], f["service"].grant()) is None


def test_unconfirmed_partial_policy_never_opens_capture(fixture: dict[str, Any]) -> None:
    f = fixture
    enable_work(f)
    policy = f["source"].completed_work
    controller = CapturePolicyController(f["service"])
    controller.disable(key="disabled")
    f["store"].append(
        "unconfirmed",
        "source_work_authorization",
        policy.model_copy(update={"authorized_at": NOW + timedelta(seconds=1)}).model_dump(
            mode="json"
        ),
        at=NOW,
    )
    assert completed_work_authorization(f["store"], f["grant"]) is None, (
        "unconfirmed source authority opened capture"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"ephemeral": True},
        {"source": "exec"},
        {"parentThreadId": "delegator"},
        {"forkedFromId": "parent"},
    ],
)
def test_completed_work_keeps_non_owner_source_exclusions(
    fixture: dict[str, Any],
    change: dict[str, Any],
) -> None:
    f = fixture
    enable_work(f)
    f["thread"].update(change)
    assert not f["source"].poll(f["grant"].issued_at, None).episodes


@pytest.mark.parametrize(
    "text",
    [
        "<heartbeat>Generated periodic instructions</heartbeat>",
        "<environment_context>Generated context</environment_context>",
        "# AGENTS.md instructions\n\n<INSTRUCTIONS>Generated policy</INSTRUCTIONS>"
        "<environment_context>Generated context</environment_context>",
        "<INSTRUCTIONS>Generated policy</INSTRUCTIONS>",
        "<turn_aborted>Generated interruption context</turn_aborted>",
        "<codex_delegation>Generated coordinator request</codex_delegation>",
        '<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>',
    ],
)
def test_native_transport_context_never_becomes_owner_work(
    fixture: dict[str, Any],
    text: str,
) -> None:
    f = fixture
    enable_work(f)
    f["thread"]["turns"][0]["items"][0]["content"][0]["text"] = text
    assert not f["source"].poll(f["grant"].issued_at, None).episodes


def test_native_question_reply_admits_answer_without_generated_question(
    fixture: dict[str, Any],
) -> None:
    f = fixture
    enable_work(f)
    f["thread"]["turns"][0]["items"][0]["content"][0]["text"] = (
        '<send_user_message_question_reply>[{"question":"Generated words",'
        '"answer":"Owner answer"}]</send_user_message_question_reply>'
    )
    episode = f["source"].poll(f["grant"].issued_at, None).episodes[0]
    assert episode.text == "Owner answer"


def test_cursor_restart_preserves_prior_conversation_checkpoints(fixture: dict[str, Any]) -> None:
    from adaptation_compiler_lab.autonomy.codex_source import HabitSourceCursorV1
    from tests.unit.autonomy.test_codex_source import BINDING

    f = fixture
    authorize(f)
    before = HabitSourceCursorV1(
        grant_digest=f["grant"].content_digest, source_binding=BINDING, next_page="older-page"
    )
    f["store"].append(
        "prior-cursor",
        "cursor",
        {"grant_id": f["grant"].grant_id, "cursor": before.model_dump_json()},
        at=NOW,
    )
    controller = CapturePolicyController(f["service"])
    preview = controller.preview([])
    controller.enable(preview["preview_token"], confirmed=True, key="start-window")
    after = HabitSourceCursorV1.model_validate_json(f["store"].latest("cursor")["cursor"])
    assert after == before.model_copy(update={"next_page": None})


def test_bad_cursor_cannot_partially_commit_source_permission(fixture: dict[str, Any]) -> None:
    f = fixture
    authorize(f)
    f["store"].append(
        "bad-cursor", "cursor", {"grant_id": f["grant"].grant_id, "cursor": "invalid"}, at=NOW
    )
    controller = CapturePolicyController(f["service"])
    preview = controller.preview([])
    head = f["store"].head_digest
    with pytest.raises(ValueError):
        controller.enable(preview["preview_token"], confirmed=True, key="start-window")
    assert f["store"].head_digest == head
    assert completed_work_authorization(f["store"], f["grant"]) is None


def test_owner_protocol_reports_actual_window_without_injecting_evidence(
    fixture: dict[str, Any],
) -> None:
    from adaptation_compiler_lab.autonomy.protocol import AutonomyProtocol

    f = fixture
    authorize(f)
    protocol = AutonomyProtocol(f["service"])
    preview = protocol.dispatch(
        "autonomy.capture.preview", {"bindings": []}, expected_digest=None, idempotency_key=None
    )
    result = protocol.dispatch(
        "autonomy.capture.enable",
        {"preview_token": preview["preview_token"], "confirmed": True},
        expected_digest=f["service"].snapshot_digest,
        idempotency_key="owner-enable",
    )
    assert result["capture_window"] == "completed_work"
    assert result["conversation_independence"] == "one_episode_per_conversation"
    assert f["service"].episodes() == {}
