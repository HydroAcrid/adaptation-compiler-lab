from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.modes import (
    FRONTEND_STUDIO_MODE,
    ModeCompositionError,
    ModePreparedTask,
    ModeReceiptStore,
    complete_mode_delivery,
    evaluate_frontend_studio_mode,
    mode_applies_to,
    prepare_mode_task,
)
from adaptation_compiler_lab.modes.models import ModeClause, ModeClauseCategory
from adaptation_compiler_lab.portability import build_personal_mode_overlay
from adaptation_compiler_lab.targets.base import sha256_text

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
CORE_DIGEST = f"sha256:{'a' * 64}"


def _signer() -> GovernanceSigner:
    return GovernanceSigner(
        Ed25519PrivateKey.from_private_bytes(b"m" * 32),
        identity_id="owner-identity",
        subject_id="owner",
    )


def _prepared(
    *, project_id: str = "kairn", task: str = "Refine the settings page"
) -> ModePreparedTask:
    return prepare_mode_task(
        FRONTEND_STUDIO_MODE,
        activation_id="mode-activation-1",
        subject_id="owner",
        project_id=project_id,
        target_family="codex",
        task=task,
        base_delivered_task=f"Current approved rules.\n\nTask:\n\n{task}",
        base_delivery_digest=sha256_text(f"Current approved rules.\n\nTask:\n\n{task}"),
        prior_core_release_digest=CORE_DIGEST,
        signer=_signer(),
        activated_at=NOW,
    )


def test_frontend_studio_conformance_matrix_passes_without_provider_calls() -> None:
    report = evaluate_frontend_studio_mode()

    assert report.valid is True
    assert report.relevant_cases_passed == 2
    assert report.neutral_controls_passed == 4
    assert report.projection_utf8_bytes <= FRONTEND_STUDIO_MODE.maximum_projection_utf8_bytes


def test_mode_is_delivered_once_and_binds_exact_task_project_and_core() -> None:
    prepared = _prepared()

    assert prepared.delivered_task.count(prepared.mode_material) == 1
    assert prepared.activation.project_id == "kairn"
    assert prepared.activation.task_digest == sha256_text("Refine the settings page")
    assert prepared.activation.prior_core_release_digest == CORE_DIGEST
    assert prepared.activation.ends_after_task is True


def test_mode_activation_signature_detects_scope_tampering() -> None:
    signer = _signer()
    prepared = _prepared()
    changed = prepared.activation.model_copy(update={"project_id": "green-meadow"})
    public_key = base64.b64encode(signer.private_key.public_key().public_bytes_raw()).decode(
        "ascii"
    )

    with pytest.raises(ValueError, match="signature"):
        verify_detached_envelope(
            changed.unsigned_payload,
            changed.signature,
            public_key_base64=public_key,
            expected_purpose="mode_activation",
        )


def test_higher_authority_claim_suppresses_only_matching_mode_default() -> None:
    prepared = prepare_mode_task(
        FRONTEND_STUDIO_MODE,
        activation_id="mode-activation-2",
        subject_id="owner",
        project_id="kairn",
        target_family="codex",
        task="Refine the settings page",
        base_delivered_task="Task: Refine the settings page",
        base_delivery_digest=sha256_text("Task: Refine the settings page"),
        prior_core_release_digest=CORE_DIGEST,
        signer=_signer(),
        activated_at=NOW,
        suppressed_claim_keys=("frontend.visual-direction",),
    )

    assert "frontend-studio-visual-direction" not in prepared.included_clause_ids
    assert len(prepared.included_clause_ids) == len(FRONTEND_STUDIO_MODE.clauses) - 1


def test_personal_overlay_replaces_matching_default_and_is_bound_to_activation() -> None:
    replacement = ModeClause(
        clause_id="personal-visual-direction",
        claim_key="frontend.visual-direction",
        category=ModeClauseCategory.VISUAL_DIRECTION,
        text="Use tactile editorial surfaces and restrained copper accents.",
    )
    overlay = build_personal_mode_overlay(
        (replacement,),
        signer=_signer(),
        package_id="owner-frontend-overlay",
        release_version="1.0.0",
        display_name="Owner frontend overlay",
        publisher_name="Owner",
        source_license="Private use only",
        base_mode_id=FRONTEND_STUDIO_MODE.mode_id,
        base_mode_version=FRONTEND_STUDIO_MODE.mode_version,
        base_mode_digest=FRONTEND_STUDIO_MODE.content_digest,
        created_at=NOW,
    )

    prepared = prepare_mode_task(
        FRONTEND_STUDIO_MODE,
        activation_id="mode-activation-overlay",
        subject_id="owner",
        project_id="kairn",
        target_family="codex",
        task="Refine the settings page",
        base_delivered_task="Task: Refine the settings page",
        base_delivery_digest=sha256_text("Task: Refine the settings page"),
        prior_core_release_digest=CORE_DIGEST,
        signer=_signer(),
        activated_at=NOW,
        personal_overlay=overlay,
    )

    assert replacement.text in prepared.mode_material
    assert "frontend-studio-visual-direction" not in prepared.included_clause_ids
    assert prepared.included_overlay_clause_ids == (replacement.clause_id,)
    assert prepared.activation.personal_overlay_digest == overlay.content_digest

    suppressed = prepare_mode_task(
        FRONTEND_STUDIO_MODE,
        activation_id="mode-activation-overlay-suppressed",
        subject_id="owner",
        project_id="kairn",
        target_family="codex",
        task="Refine the settings page",
        base_delivered_task="Task: Refine the settings page",
        base_delivery_digest=sha256_text("Task: Refine the settings page"),
        prior_core_release_digest=CORE_DIGEST,
        signer=_signer(),
        activated_at=NOW,
        suppressed_claim_keys=(replacement.claim_key,),
        personal_overlay=overlay,
    )
    assert suppressed.included_overlay_clause_ids == ()
    assert suppressed.activation.personal_overlay_digest == overlay.content_digest


def test_personal_overlay_rejects_wrong_owner_or_mode() -> None:
    overlay = build_personal_mode_overlay(
        (
            ModeClause(
                clause_id="personal-motion",
                claim_key="frontend.motion",
                category=ModeClauseCategory.VISUAL_DIRECTION,
                text="Prefer almost no motion.",
            ),
        ),
        signer=_signer(),
        package_id="owner-frontend-overlay",
        release_version="1.0.0",
        display_name="Owner frontend overlay",
        publisher_name="Owner",
        source_license="Private use only",
        base_mode_id=FRONTEND_STUDIO_MODE.mode_id,
        base_mode_version=FRONTEND_STUDIO_MODE.mode_version,
        base_mode_digest=FRONTEND_STUDIO_MODE.content_digest,
        created_at=NOW,
    )

    with pytest.raises(ModeCompositionError, match="owner and exact Mode"):
        prepare_mode_task(
            FRONTEND_STUDIO_MODE,
            activation_id="mode-activation-wrong-owner",
            subject_id="another-owner",
            project_id="kairn",
            target_family="codex",
            task="Refine the settings page",
            base_delivered_task="Task: Refine the settings page",
            base_delivery_digest=sha256_text("Task: Refine the settings page"),
            prior_core_release_digest=CORE_DIGEST,
            signer=_signer(),
            activated_at=NOW,
            personal_overlay=overlay,
        )


def test_mode_rejects_other_target_and_unknown_suppression() -> None:
    with pytest.raises(ModeCompositionError, match="incompatible"):
        prepare_mode_task(
            FRONTEND_STUDIO_MODE,
            activation_id="mode-activation-3",
            subject_id="owner",
            project_id="kairn",
            target_family="copilot",
            task="Refine the settings page",
            base_delivered_task="Task: Refine the settings page",
            base_delivery_digest=sha256_text("Task: Refine the settings page"),
            prior_core_release_digest=CORE_DIGEST,
            signer=_signer(),
            activated_at=NOW,
        )
    with pytest.raises(ModeCompositionError, match="unknown claim"):
        prepare_mode_task(
            FRONTEND_STUDIO_MODE,
            activation_id="mode-activation-4",
            subject_id="owner",
            project_id="kairn",
            target_family="codex",
            task="Refine the settings page",
            base_delivered_task="Task: Refine the settings page",
            base_delivery_digest=sha256_text("Task: Refine the settings page"),
            prior_core_release_digest=CORE_DIGEST,
            signer=_signer(),
            activated_at=NOW,
            suppressed_claim_keys=("unknown.claim",),
        )


def test_completion_restores_exact_core_and_leaves_no_mode_clauses() -> None:
    prepared = _prepared()
    receipt = complete_mode_delivery(
        prepared,
        outcome="completed",
        restored_core_release_digest=CORE_DIGEST,
        signer=_signer(),
        deactivated_at=NOW + timedelta(minutes=10),
    )

    assert receipt.restored_core_release_digest == CORE_DIGEST
    assert receipt.mode_clauses_remaining == 0

    with pytest.raises(ModeCompositionError, match="restore"):
        complete_mode_delivery(
            prepared,
            outcome="completed",
            restored_core_release_digest=f"sha256:{'b' * 64}",
            signer=_signer(),
            deactivated_at=NOW + timedelta(minutes=10),
        )


def test_mode_receipts_are_append_only_raw_free_and_idempotent(tmp_path: Path) -> None:
    prepared = _prepared()
    completed = complete_mode_delivery(
        prepared,
        outcome="completed",
        restored_core_release_digest=CORE_DIGEST,
        signer=_signer(),
        deactivated_at=NOW + timedelta(minutes=10),
    )
    store = ModeReceiptStore(tmp_path / "mode-receipts")

    store.append_activation(prepared.activation, prepared.delivery)
    store.append_activation(prepared.activation, prepared.delivery)
    store.append_deactivation(completed)
    store.append_deactivation(completed)

    assert store.lifecycle_count() == (1, 1)
    stored = "\n".join(
        path.read_text(encoding="utf-8") for path in (tmp_path / "mode-receipts").iterdir()
    )
    assert "Refine the settings page" not in stored
    assert "Current approved rules" not in stored


def test_activation_never_leaks_across_task_project_target_or_expiry() -> None:
    prepared = _prepared()

    assert mode_applies_to(
        prepared.activation,
        FRONTEND_STUDIO_MODE,
        project_id="kairn",
        target_family="codex",
        task="Refine the settings page",
        evaluated_at=NOW + timedelta(minutes=1),
    )
    assert not mode_applies_to(
        prepared.activation,
        FRONTEND_STUDIO_MODE,
        project_id="green-meadow",
        target_family="codex",
        task="Refine the settings page",
        evaluated_at=NOW + timedelta(minutes=1),
    )
    assert not mode_applies_to(
        prepared.activation,
        FRONTEND_STUDIO_MODE,
        project_id="kairn",
        target_family="codex",
        task="Investigate a database timeout",
        evaluated_at=NOW + timedelta(minutes=1),
    )
    assert not mode_applies_to(
        prepared.activation,
        FRONTEND_STUDIO_MODE,
        project_id="kairn",
        target_family="codex",
        task="Refine the settings page",
        evaluated_at=NOW + timedelta(hours=5),
    )
