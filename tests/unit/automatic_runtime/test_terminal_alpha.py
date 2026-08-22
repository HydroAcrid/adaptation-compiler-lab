"""Terminal-alpha rendering and command-boundary tests over disposable ledgers."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from adaptation_compiler_lab import temper_cli
from adaptation_compiler_lab.automatic_runtime import AutomaticRuntimeState, initial_runtime_state
from adaptation_compiler_lab.automatic_runtime.gate import CodexDogfoodGateReport
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackDetectorMode,
    RuntimeTargetDeliveryAcknowledgement,
)
from adaptation_compiler_lab.automatic_runtime.product_dogfood import (
    ReviewModeDogfoodSnapshot,
    TerminalAlphaSnapshot,
    build_review_mode_dogfood_snapshot,
    build_terminal_alpha_snapshot,
)
from adaptation_compiler_lab.automatic_runtime.terminal_ui import (
    render_plain,
    render_terminal,
)
from adaptation_compiler_lab.domain import ApprovalDecision, TaskRecordRef
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.targets.base import sha256_text

from .test_runtime import NOW, _context, _observation, _review_item, _runtime

SNAPSHOT_ROOT = Path(__file__).parents[2] / "snapshots" / "terminal_alpha"


def _empty_snapshot(tmp_path: Path) -> tuple[TerminalAlphaSnapshot, AutomaticRuntimeState]:
    _runtime_service, policy = _runtime(tmp_path)
    state = initial_runtime_state(policy)
    path = tmp_path / "empty-runtime.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(state)
    review = build_review_mode_dogfood_snapshot(
        ledger,
        subject_id="kevin",
        generated_at=NOW,
        detector_mode=FeedbackDetectorMode.REVIEW,
        credential_enrolled=True,
        watcher_active=True,
    )
    return (
        build_terminal_alpha_snapshot(
            review,
            state=state,
            configured_project_ids=("kairn", "green-meadow"),
        ),
        state,
    )


def _current_gate_snapshot(tmp_path: Path) -> TerminalAlphaSnapshot:
    empty, state = _empty_snapshot(tmp_path)
    report_data = empty.review_mode.gate.model_dump(mode="python")
    report_data.update(
        {
            "eligible_interaction_count": 13,
            "active_date_count": 4,
            "assessed_interaction_count": 13,
            "correct_learning_count": 11,
            "false_learning_count": 1,
            "missed_learning_count": 1,
            "promoted_count": 10,
            "review_required_count": 1,
            "resolved_review_count": 1,
            "approved_review_count": 1,
            "unresolved_review_count": 0,
            "activation_count": 2,
            "completed_activation_count": 2,
            "rated_activation_count": 2,
            "helped_count": 1,
            "irrelevant_count": 1,
            "correct_activation_count": 1,
            "false_activation_count": 1,
            "pack_bytes_by_activation": (181, 142),
            "automatic_actions": 15,
            "manual_review_touches": 1,
            "remaining_interactions": 7,
            "evidence_ready": False,
        }
    )
    gate = CodexDogfoodGateReport.model_validate(report_data)
    review_data = empty.review_mode.model_dump(mode="python")
    review_data["gate"] = gate
    review = ReviewModeDogfoodSnapshot.model_validate(review_data)
    return build_terminal_alpha_snapshot(
        review,
        state=state,
        configured_project_ids=("kairn", "green-meadow"),
    )


def _review_and_active_snapshots(
    tmp_path: Path,
) -> tuple[TerminalAlphaSnapshot, TerminalAlphaSnapshot]:
    runtime, policy = _runtime(tmp_path)
    state = initial_runtime_state(policy)
    path = tmp_path / "review-runtime.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(state)
    learning = runtime.learn(
        _observation(1, "Rule: install a plugin and give it network access"),
        state=state,
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    item = _review_item(learning)
    ledger.append_learning(learning.cycle, state, review_item=item)
    pending_review = build_review_mode_dogfood_snapshot(
        ledger,
        subject_id="kevin",
        generated_at=NOW + timedelta(minutes=2),
        detector_mode=FeedbackDetectorMode.REVIEW,
        credential_enrolled=True,
        watcher_active=False,
    )
    pending = build_terminal_alpha_snapshot(
        pending_review,
        state=state,
        configured_project_ids=("ordinary-project",),
    )

    approved = runtime.resolve_review(
        item,
        learning.cycle,
        state=state,
        decision=ApprovalDecision.APPROVED,
        resolved_at=NOW + timedelta(minutes=2, seconds=10),
    )
    ledger.append_learning_review_resolution(
        approved.resolution,
        approved.state,
        release_event=approved.release_event,
    )
    prepared = runtime.activate(
        activation_id="activation-terminal-1",
        task_ref=TaskRecordRef(record_id="task-terminal-1", record_version="1.0.0"),
        state=approved.state,
        context=_context(3, project_id="ordinary-project"),
        target_task="Prepare the plugin handoff.",
        activated_at=NOW + timedelta(minutes=3),
    )
    ledger.append_activation(prepared)
    ledger.acknowledge_delivery(
        RuntimeTargetDeliveryAcknowledgement(
            acknowledgement_id="ack-terminal-1",
            activation_id="activation-terminal-1",
            subject_id="kevin",
            target_family="codex",
            activation_digest=prepared.activation.content_digest,
            external_session_digest=sha256_text("terminal-session-1"),
            external_turn_digest=sha256_text("terminal-turn-1"),
            result_digest=sha256_text("terminal-result-1"),
            status="completed",
            acknowledged_at=NOW + timedelta(minutes=4),
        )
    )
    active_review = build_review_mode_dogfood_snapshot(
        ledger,
        subject_id="kevin",
        generated_at=NOW + timedelta(minutes=5),
        detector_mode=FeedbackDetectorMode.REVIEW,
        credential_enrolled=True,
        watcher_active=True,
    )
    active = build_terminal_alpha_snapshot(
        active_review,
        state=approved.state,
        configured_project_ids=("ordinary-project",),
    )
    return pending, active


@pytest.mark.parametrize(
    ("fixture_name", "view", "snapshot_index"),
    (
        ("status.txt", "status", None),
        ("review.txt", "review", 0),
        ("adaptations.txt", "adaptations", 1),
    ),
)
def test_terminal_views_match_reviewed_snapshots(
    tmp_path: Path,
    fixture_name: str,
    view: str,
    snapshot_index: int | None,
) -> None:
    if snapshot_index is None:
        snapshot = _current_gate_snapshot(tmp_path)
    else:
        snapshot = _review_and_active_snapshots(tmp_path)[snapshot_index]

    rendered = render_terminal(snapshot, view=view, width=88, color=False)  # type: ignore[arg-type]

    assert rendered == (SNAPSHOT_ROOT / fixture_name).read_text(encoding="utf-8")


def test_plain_phone_view_is_stable_raw_free_and_ansi_free(tmp_path: Path) -> None:
    pending, active = _review_and_active_snapshots(tmp_path)
    rendered = render_plain(pending, view="review") + render_plain(active, view="status")

    assert "Rule:" not in rendered
    assert "supporting_quote" not in rendered
    assert "locator" not in rendered
    assert "\x1b[" not in rendered
    assert "Install a plugin and give it network access" in rendered
    assert "Approval authorizes" not in rendered
    assert render_plain(active, view="status") == (SNAPSHOT_ROOT / "phone-status.txt").read_text(
        encoding="utf-8"
    )


def test_terminal_views_respect_eighty_column_floor(tmp_path: Path) -> None:
    pending, active = _review_and_active_snapshots(tmp_path)
    for snapshot in (pending, active, _current_gate_snapshot(tmp_path)):
        for view in ("status", "review", "adaptations", "history", "health", "gate"):
            rendered = render_terminal(snapshot, view=view, width=80, color=False)
            assert max(map(len, rendered.splitlines()), default=0) <= 80


def test_renderer_has_no_storage_or_capture_dependency() -> None:
    source = Path(temper_cli.__file__).with_name("automatic_runtime") / "terminal_ui.py"
    text = source.read_text(encoding="utf-8")

    for forbidden in (
        "persistence",
        "LocalRawPayloadStore",
        "SqliteUnitOfWorkFactory",
        "connectors",
        "runners",
    ):
        assert forbidden not in text


def test_product_cli_help_and_missing_configuration_are_actionable() -> None:
    runner = CliRunner()
    help_result = runner.invoke(temper_cli.app, ["--help"])
    missing = runner.invoke(temper_cli.app, ["status"])

    assert help_result.exit_code == 0
    assert "approve" in help_result.output
    assert "undo" in help_result.output
    assert missing.exit_code == 1
    assert "pass --config or set TEMPER_CONFIG_PATH" in missing.output


def test_product_cli_reads_snapshot_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "temper.json"
    config.write_text("{}", encoding="utf-8")
    snapshot = _current_gate_snapshot(tmp_path)
    monkeypatch.setattr(temper_cli, "_load", lambda _settings: snapshot)

    result = CliRunner().invoke(
        temper_cli.app,
        ["--config", str(config), "--format", "plain", "status"],
    )

    assert result.exit_code == 0, result.output
    assert "Interactions: 13/20" in result.output
    assert "Allowance false_activation: 1/1 (used)" in result.output


def test_product_cli_requires_future_use_and_undo_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "temper.json"
    config.write_text("{}", encoding="utf-8")
    called = False

    def reject_unconfirmed(*_args: object, confirm_future_use: bool, **_kwargs: object) -> object:
        nonlocal called
        called = True
        if not confirm_future_use:
            raise ValueError("approval requires explicit future-use confirmation")
        return {"generation": 1}

    monkeypatch.setattr(temper_cli, "resolve_codex_dogfood_review", reject_unconfirmed)
    runner = CliRunner()
    approval = runner.invoke(
        temper_cli.app,
        [
            "--config",
            str(config),
            "approve",
            "queue-1",
            "--proposal-digest",
            "sha256:" + "a" * 64,
        ],
    )
    undo = runner.invoke(
        temper_cli.app,
        ["--config", str(config), "undo", "artifact-1"],
    )

    assert approval.exit_code == 1
    assert called
    assert "future-use confirmation" in approval.output
    assert undo.exit_code == 1
    assert "undo requires --confirm" in undo.output
