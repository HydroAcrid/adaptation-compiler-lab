from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.autonomy.analyzer import SchemaBoundHabitSensor
from adaptation_compiler_lab.autonomy.evaluation import load_frozen_scenarios, score_hypotheses
from adaptation_compiler_lab.autonomy.models import (
    CalibrationReleaseV1,
    HabitOutcomeV1,
    HabitProposalV1,
    HabitState,
    InputOrigin,
    StyleCategory,
    StyleEpisodeV1,
    TaskClass,
)
from adaptation_compiler_lab.autonomy.protocol import AutonomyProtocol
from adaptation_compiler_lab.autonomy.provenance import codex_message_origin
from adaptation_compiler_lab.autonomy.retention import purge_expired_raw
from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.autonomy.styles import StyleKey
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker, CapturePage
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey

DIGEST = "sha256:" + "a" * 64
NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


@dataclass
class Clock:
    value: datetime = NOW

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture
def app(tmp_path: Path) -> tuple[AutonomyApplicationService, Clock]:
    clock = Clock()
    home = tmp_path / "codex"
    home.mkdir()
    (home / "AGENTS.md").write_bytes(b"# Owner guidance\r\nPreserve this exactly.\r\n")
    project = tmp_path / "project"
    project.mkdir()
    store = AutonomyStore(
        tmp_path / "private" / "habits.sqlite3",
        signer=GovernanceSigner(Ed25519PrivateKey.generate(), "owner", "subject"),
        raw_store=LocalRawPayloadStore(
            tmp_path / "private" / "raw", encryption_key=RawEncryptionKey(b"k" * 32)
        ),
    )
    service = AutonomyApplicationService(
        store=store,
        projects={"project": project},
        codex_home=home,
        clock=clock,
        provenance_verifier=lambda episode: episode.provenance_digest == DIGEST,
        native_conflict_checker=lambda habit: False,
        calibration_verifier=lambda release: release.analyzer_digest == DIGEST,
        outcome_verifier=lambda outcome: outcome.check_digest == DIGEST,
    )
    preview = service.preview_grant(("project",), (StyleCategory.COMMUNICATION_DETAIL,))
    service.confirm_grant(
        preview["preview_token"], confirmed=True, idempotency_key="grant-confirmed"
    )
    return service, clock


def episode(index: int, clock: Clock, **changes: Any) -> StyleEpisodeV1:
    data = {
        "episode_id": f"task-{index}",
        "source_task_id": f"source-task-{index}",
        "observation_ids": (f"message-{index}",),
        "project_id": "project",
        "source_client": "codex-interactive",
        "origin": InputOrigin.HUMAN,
        "provenance_digest": DIGEST,
        "created_at": clock.value,
        "completed_at": clock.value,
        "text": "Can you shorten the progress update?",
    }
    return StyleEpisodeV1(**{**data, **changes})


def calibrated(service: AutonomyApplicationService, clock: Clock) -> None:
    service.install_calibration(
        CalibrationReleaseV1(
            evaluation_version="habit-eval-v1",
            dataset_digest=DIGEST,
            analyzer_digest=DIGEST,
            precision=0.98,
            recall=0.90,
            disallowed_promotions=0,
            wrong_scope_activations=0,
            lifecycle_checks_passed=True,
            synthetic=True,
            recorded_at=clock.value,
        )
    )


def proposal(ids: tuple[str, ...], **changes: Any) -> HabitProposalV1:
    return HabitProposalV1(
        **{
            "behavior": "Prefer concise progress updates.",
            "style_key": StyleKey.CONCISE_PROGRESS,
            "category": StyleCategory.COMMUNICATION_DETAIL,
            "task_class": TaskClass.PROGRESS_UPDATE,
            "evidence_episode_ids": ids,
            "evaluation_version": "habit-eval-v1",
            **changes,
        }
    )


def trial(service: AutonomyApplicationService, clock: Clock) -> str:
    calibrated(service, clock)
    for index in range(3):
        clock.value = NOW + timedelta(days=index // 2, minutes=index)
        service.ingest_episode(episode(index, clock))
    return service.record_proposal(proposal(("task-0", "task-1", "task-2"))).habit_id


def test_grant_persists_but_lease_renews_and_capture_stays_shadow(app: Any) -> None:
    service, clock = app
    original = service.ensure_lease()
    clock.value += timedelta(days=40)
    renewed = service.ensure_lease()
    assert service.grant() is not None
    assert renewed.grant_digest == original.grant_digest
    assert renewed.issued_at > original.expires_at
    assert service.status()["mode"] == "shadow"
    assert service.status()["raw_retention_days"] == 30


@pytest.mark.parametrize(
    "origin",
    [
        InputOrigin.AGENT,
        InputOrigin.DELEGATED,
        InputOrigin.COPIED,
        InputOrigin.INJECTED,
        InputOrigin.UNKNOWN,
    ],
)
def test_nonhuman_messages_never_enter_learning(app: Any, origin: InputOrigin) -> None:
    service, clock = app
    assert not service.ingest_episode(episode(0, clock, origin=origin))
    assert not service.episodes()


def test_role_alone_or_unknown_provenance_is_insufficient(app: Any) -> None:
    service, clock = app
    assert not service.ingest_episode(episode(0, clock, provenance_digest=None))
    service.provenance_verifier = None
    assert not service.ingest_episode(episode(0, clock))
    assert not service.automatic_ready()


def test_replay_is_idempotent_and_raw_text_is_encrypted(app: Any) -> None:
    service, clock = app
    value = episode(0, clock)
    assert service.ingest_episode(value)
    assert not service.ingest_episode(value)
    assert "shorten" not in service.store.path.read_bytes().decode("latin1")
    paths = [path for path in service.store.raw_store.root.rglob("*") if path.is_file()]
    assert paths
    for path in paths:
        assert b"Can you shorten" not in path.read_bytes()
        assert path.read_bytes().startswith(b"ACLAB-RAW-1")
    with pytest.raises(AutonomyIntegrityError, match="replay content"):
        service.ingest_episode(value.model_copy(update={"text": "different message"}))


def test_repetition_within_one_task_does_not_start_trial(app: Any) -> None:
    service, clock = app
    calibrated(service, clock)
    service.ingest_episode(episode(0, clock))
    habit = service.record_proposal(proposal(("task-0", "task-0", "task-0")))
    assert habit.state is HabitState.PROVISIONAL


def test_independent_tasks_across_two_dates_can_trial_without_user_preference_phrase(
    app: Any,
) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    assert service.hypotheses()[0].habit_id == habit_id
    assert service.hypotheses()[0].state is HabitState.TRIAL
    assert service.hypotheses()[0].origin == "inferred"
    assert service.applicability("unrelated", TaskClass.PROGRESS_UPDATE)["applies"] == []


def test_native_conflict_or_missing_calibration_withholds_trial(app: Any) -> None:
    service, clock = app
    for index in range(3):
        clock.value = NOW + timedelta(days=index)
        service.ingest_episode(episode(index, clock))
    assert (
        service.record_proposal(proposal(("task-0", "task-1", "task-2"))).state
        is HabitState.PROVISIONAL
    )
    calibrated(service, clock)
    service.native_conflict_checker = lambda habit: True
    assert (
        service.record_proposal(proposal(("task-0", "task-1", "task-2"))).state
        is HabitState.PROVISIONAL
    )


def test_budget_unknown_low_exhausted_and_tick_replay(app: Any) -> None:
    service, clock = app
    assert not service.budget_available(None)
    assert not service.budget_available(19)
    for index in range(12):
        assert service.budget_available(50)
        service.begin_analysis(50, key=f"analysis-{index}")
        assert not service.budget_available(50)
        clock.value += timedelta(minutes=5)
    assert not service.budget_available(50)
    clock.value += timedelta(days=1)
    assert service.budget_available(50)


def test_three_checked_opportunities_can_promote_and_unknown_outcomes_do_not(app: Any) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    for index, followed in enumerate((True, True, None)):
        service.ingest_episode(episode(20 + index, clock, episode_id=f"opportunity-{index}"))
        service.record_outcome(
            HabitOutcomeV1(
                outcome_id=f"outcome-{index}",
                habit_id=habit_id,
                habit_revision=1,
                episode_id=f"opportunity-{index}",
                project_id="project",
                task_class=TaskClass.PROGRESS_UPDATE,
                occurred_at=clock.value,
                followed=followed,
                delivered=True if followed is not None else None,
                assessment_origin="unknown" if followed is None else "verified_check",
                check_digest=None if followed is None else DIGEST,
            )
        )
    assert service.hypotheses()[0].state is HabitState.TRIAL
    service.ingest_episode(episode(25, clock, episode_id="opportunity-last"))
    service.record_outcome(
        HabitOutcomeV1(
            outcome_id="last",
            habit_id=habit_id,
            habit_revision=1,
            episode_id="opportunity-last",
            project_id="project",
            task_class=TaskClass.PROGRESS_UPDATE,
            occurred_at=clock.value,
            followed=False,
            delivered=True,
            assessment_origin="verified_check",
            check_digest=DIGEST,
        )
    )
    assert service.hypotheses()[0].state is HabitState.ACTIVE


def test_contradiction_pauses_and_owner_revoke_blocks_regeneration(app: Any) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    service.ingest_episode(episode(4, clock, text="Please make these updates more detailed."))
    habit = service.record_proposal(
        proposal(("task-0", "task-1", "task-2"), contradictory_episode_ids=("task-4",))
    )
    assert habit.state is HabitState.PAUSED
    service.retire(habit_id, key="undo")
    with pytest.raises(AutonomyIntegrityError, match="cannot regenerate"):
        service.record_proposal(proposal(("task-0", "task-1", "task-2")))


def test_publication_preserves_owner_bytes_and_does_not_claim_delivery(app: Any) -> None:
    service, clock = app
    trial(service, clock)
    path = service.publisher.home / "AGENTS.md"
    before = path.read_bytes()
    service.set_switch("personalization", True, key="start-serving")
    result = service.publish()
    assert result["status"] == "published"
    assert path.read_bytes().startswith(before)
    assert len(path.read_bytes()) - len(before) <= 1_504
    assert service.status()["delivery_confirmed"] is False
    service.set_switch("personalization", False, key="stop-serving")
    assert b"Prefer concise" not in path.read_bytes()
    assert path.read_bytes().startswith(before)


def test_manual_edit_or_removed_managed_section_is_never_overwritten(app: Any) -> None:
    service, clock = app
    trial(service, clock)
    service.set_switch("personalization", True, key="serve")
    service.publish()
    path = service.publisher.home / "AGENTS.md"
    changed = path.read_bytes().replace(b"Prefer concise", b"Owner changed this")
    path.write_bytes(changed)
    with pytest.raises(AutonomyIntegrityError, match="edited or removed"):
        service.publish()
    assert path.read_bytes() == changed


def test_signed_history_cannot_be_updated_or_deleted(app: Any) -> None:
    service, _clock = app
    with sqlite3.connect(service.store.path) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            connection.execute("UPDATE autonomy_events SET payload='{}'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            connection.execute("DELETE FROM autonomy_events")
    assert service.store.events()


def test_failure_recording_publication_restores_original_bytes(app: Any, monkeypatch: Any) -> None:
    service, clock = app
    trial(service, clock)
    service.set_switch("personalization", True, key="serve")
    path = service.publisher.home / "AGENTS.md"
    original = path.read_bytes()
    append = service.store.append

    def refuse(key: str, kind: str, payload: Any, **kwargs: Any) -> bool:
        if kind == "publication":
            raise OSError("ledger unavailable")
        return append(key, kind, payload, **kwargs)

    monkeypatch.setattr(service.store, "append", refuse)
    with pytest.raises(OSError, match="unavailable"):
        service.publish()
    assert path.read_bytes() == original


def test_expired_trials_retire_and_pause_stops_capture(app: Any) -> None:
    service, clock = app
    trial(service, clock)
    clock.value += timedelta(days=15)
    service.expire_trials()
    assert service.hypotheses()[0].state is HabitState.RETIRED
    service.set_switch("learning", False, key="pause")
    assert not service.ingest_episode(episode(9, clock))
    service.revoke_grant(key="revoke")
    assert service.grant() is None


def test_snapshot_never_contains_raw_episode_text_or_native_destination(app: Any) -> None:
    service, clock = app
    service.ingest_episode(episode(0, clock))
    payload = json.dumps(service.status())
    assert "Can you shorten" not in payload
    assert str(service.publisher.home) not in payload
    assert service.status()["raw_payloads_exposed"] is False


def test_aliases_and_shared_observations_cannot_manufacture_tasks(app: Any) -> None:
    service, clock = app
    assert service.ingest_episode(episode(0, clock))
    assert not service.ingest_episode(episode(1, clock, source_task_id="source-task-0"))
    with pytest.raises(AutonomyIntegrityError, match="independent tasks"):
        service.ingest_episode(episode(2, clock, observation_ids=("message-0",)))


def test_prospective_cutoff_future_time_and_paused_store(app: Any) -> None:
    service, clock = app
    assert not service.ingest_episode(episode(0, clock, created_at=NOW - timedelta(days=1)))
    assert not service.ingest_episode(episode(1, clock, completed_at=NOW + timedelta(seconds=1)))
    service.secure_store_available = lambda: False
    with pytest.raises(AutonomyIntegrityError, match="secure store"):
        service.ingest_episode(episode(2, clock))
    assert not service.episodes()


def test_revoke_completes_even_when_external_edit_prevents_cleanup(app: Any) -> None:
    service, clock = app
    trial(service, clock)
    service.set_switch("personalization", True, key="serve")
    service.publish()
    path = service.publisher.home / "AGENTS.md"
    changed = path.read_bytes().replace(b"Prefer concise", b"Owner edited")
    path.write_bytes(changed)
    service.revoke_grant(key="revoke-after-edit")
    assert service.grant() is None
    assert not service.switch("learning")
    assert path.read_bytes() == changed
    assert service.status()["publication_needs_attention"]


def test_retention_deletes_only_expired_ciphertext_and_preserves_metadata(app: Any) -> None:
    service, clock = app
    service.ingest_episode(episode(0, clock))
    old = service.episodes()["task-0"]["raw_ref"]
    clock.value += timedelta(days=29)
    service.ingest_episode(episode(1, clock))
    recent = service.episodes()["task-1"]["raw_ref"]
    assert purge_expired_raw(service.store, now=clock.value) == 0
    clock.value += timedelta(days=2)
    assert purge_expired_raw(service.store, now=clock.value) == 1
    assert not (service.store.raw_store.root / old["relative_path"]).exists()
    assert service.store.raw(recent)
    assert set(service.episodes()) == {"task-0", "task-1"}
    assert purge_expired_raw(service.store, now=clock.value) == 0


def test_protocol_has_closed_surface_digest_binding_and_replays(app: Any) -> None:
    service, _clock = app
    protocol = AutonomyProtocol(service)

    def call(
        method: str, params: Any = None, *, digest: str | None = None, key: str | None = None
    ) -> Any:
        return protocol.dispatch(method, params or {}, expected_digest=digest, idempotency_key=key)

    for method in (
        "autonomy.episode.ingest",
        "autonomy.calibration.install",
        "autonomy.proposal.record",
    ):
        with pytest.raises(AutonomyIntegrityError, match="unsupported"):
            call(method)
    with pytest.raises(AutonomyIntegrityError, match="idempotency"):
        call("autonomy.learning.pause")
    with pytest.raises(AutonomyIntegrityError, match="state changed"):
        call("autonomy.learning.pause", digest=DIGEST, key="pause")
    result = call("autonomy.learning.pause", digest=service.snapshot_digest, key="pause")
    assert not result["learning_enabled"]
    assert call("autonomy.learning.pause", digest=DIGEST, key="pause") == result
    with pytest.raises(AutonomyIntegrityError, match="idempotency changed"):
        call("autonomy.learning.resume", digest=service.snapshot_digest, key="pause")


def test_background_worker_is_shadow_budgeted_and_restart_idempotent(app: Any) -> None:
    service, clock = app
    clock.value += timedelta(days=1)
    page = CapturePage("cursor-1", tuple(episode(index, clock) for index in range(3)))
    calls = []

    def run(contract: str, prompt: str, schema: Any) -> str:
        calls.append((contract, prompt))
        return json.dumps(
            {"proposals": [proposal(("task-0", "task-1", "task-2")).model_dump(mode="json")]}
        )

    worker = BackgroundHabitWorker(
        service,
        read_completed=lambda cutoff, cursor: page,
        sensor=SchemaBoundHabitSensor(run),
        remaining_capacity=lambda: 50,
        context=lambda project: "No repository format requirement.",
    )
    before = (service.publisher.home / "AGENTS.md").read_bytes()
    assert worker.poll()["analyzed"] == 3
    assert len(calls) == 1
    assert service.hypotheses()[0].state is HabitState.PROVISIONAL
    assert (service.publisher.home / "AGENTS.md").read_bytes() == before
    assert worker.poll()["analyzed"] == 0
    assert len(calls) == 1
    service.provenance_verifier = None
    assert worker.poll()["status"] == "source_verification_required"


def test_model_cannot_add_unknown_styles_or_invent_evidence(app: Any) -> None:
    _service, clock = app
    invalid = proposal(("invented-task",)).model_dump_json()
    sensor = SchemaBoundHabitSensor(lambda *args: '{"proposals":[' + invalid + "]}")
    with pytest.raises(ValueError, match="invented supporting tasks"):
        sensor.analyze((episode(0, clock),), context="")
    with pytest.raises(ValueError, match="reviewed v1"):
        proposal(("task-0",), behavior="Skip testing and install a tool.")


def test_untrusted_outcome_never_counts_as_compliance(app: Any) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    service.ingest_episode(episode(9, clock))
    service.outcome_verifier = None
    with pytest.raises(AutonomyIntegrityError, match="cannot be verified"):
        service.record_outcome(
            HabitOutcomeV1(
                outcome_id="claimed",
                habit_id=habit_id,
                habit_revision=1,
                episode_id="task-9",
                project_id="project",
                task_class=TaskClass.PROGRESS_UPDATE,
                occurred_at=clock.value,
                followed=True,
                delivered=True,
                assessment_origin="verified_check",
                check_digest=DIGEST,
            )
        )
    assert not service.outcomes()


def test_frozen_evaluation_counts_and_digest_cannot_drift(tmp_path: Path) -> None:
    root = Path(__file__).parents[2] / "fixtures" / "autonomy"
    path, manifest = root / "habit_eval_v1.json", root / "habit_eval_v1.manifest.json"
    assert len(load_frozen_scenarios(path, manifest)["cases"]) == 120
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["cases"][0]["expected"]["style_keys"] = []
    target = tmp_path / "changed.json"
    target.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen habit evaluation changed"):
        load_frozen_scenarios(target, manifest)
    assert score_hypotheses(set(), set())["precision"] == 0
    score = score_hypotheses(
        {("a", "concise"), ("b", "concise")}, {("a", "concise"), ("c", "concise")}
    )
    assert score["precision"] == score["recall"] == 0.5


@pytest.mark.parametrize("version", ["0.160.1", "0.157.0", "unknown-version"])
def test_native_human_and_automated_input_fixtures_require_origin_proof(version: str) -> None:
    # Both a human and send_message_to_thread can produce this public-schema shape.
    # Fixture ground truth is deliberately outside the source record, so it cannot be
    # mistaken for production attestation. An opaque clientId never turns into proof.
    for ground_truth in ("human", "delegated", "programmatic"):
        item = {
            "type": "userMessage",
            "id": "fixture-message",
            "clientId": "opaque-client-id",
            "content": [{"type": "text", "text": "Shorten that progress update."}],
        }
        assert ground_truth  # Ground truth is fixture-only.
        assert codex_message_origin(item, client_version=version) is InputOrigin.UNKNOWN
