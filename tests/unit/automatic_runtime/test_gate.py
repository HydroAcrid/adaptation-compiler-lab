"""Ordinary-use Codex dogfood gate reporting tests."""

from __future__ import annotations

import base64
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.automatic_runtime import (
    CodexDogfoodGateReport,
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeTargetDeliveryAcknowledgement,
    build_codex_dogfood_gate_report,
    freeze_codex_dogfood_gate,
    initial_runtime_state,
)
from adaptation_compiler_lab.domain import ApprovalDecision, TaskRecordRef
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    SignatureVerificationError,
    verify_detached_envelope,
)
from adaptation_compiler_lab.targets.base import sha256_text
from tests.unit.automatic_runtime.test_runtime import (
    NOW,
    _context,
    _observation,
    _review_item,
    _runtime,
)


def test_gate_report_measures_false_learning_and_false_activation(
    tmp_path: Path,
) -> None:
    runtime, policy = _runtime(tmp_path)
    learning = runtime.learn(
        _observation(1, "I prefer purpose before commands"),
        state=initial_runtime_state(policy),
        processed_at=NOW + timedelta(minutes=2),
    )
    assessment = RuntimeLearningAssessment(
        assessment_id="assessment-1",
        subject_id="kevin",
        cycle_id=learning.cycle.cycle_id,
        cycle_digest=learning.cycle.content_digest,
        outcome=RuntimeLearningAssessmentOutcome.FALSE_POSITIVE,
        recorded_at=NOW + timedelta(minutes=2, seconds=1),
    )
    prepared = runtime.activate(
        activation_id="activation-1",
        task_ref=TaskRecordRef(record_id="task-1", record_version="1.0.0"),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Prepare the handoff.",
        activated_at=NOW + timedelta(minutes=2, seconds=2),
    )
    acknowledgement = RuntimeTargetDeliveryAcknowledgement(
        acknowledgement_id="acknowledgement-1",
        activation_id=prepared.activation.activation_id,
        subject_id="kevin",
        target_family="codex",
        activation_digest=prepared.activation.content_digest,
        external_session_digest=sha256_text("session-1"),
        external_turn_digest=sha256_text("turn-1"),
        result_digest=sha256_text("result-1"),
        status="completed",
        acknowledged_at=NOW + timedelta(minutes=2, seconds=3),
    )
    feedback = RuntimeActivationFeedback(
        feedback_id="feedback-1",
        subject_id="kevin",
        cycle_id=prepared.activation.activation_id,
        delivery_receipt_digest=prepared.activation.delivery_receipt_digest,
        outcome=RuntimeFeedbackOutcome.IRRELEVANT,
        relevant_artifact_ids=(),
        activated_artifact_ids=prepared.activation.active_artifact_ids,
        correction_key="purpose-order",
        recorded_at=NOW + timedelta(minutes=2, seconds=4),
    )

    report = build_codex_dogfood_gate_report(
        subject_id="kevin",
        learning_cycles=(learning.cycle,),
        learning_assessments=(assessment,),
        activations=(prepared.activation,),
        acknowledgements=(acknowledgement,),
        activation_feedback=(feedback,),
        generated_at=NOW + timedelta(minutes=2, seconds=5),
        goal_interaction_count=1,
        minimum_active_dates=1,
        minimum_activation_count=1,
    )

    assert report.evidence_ready is True
    assert report.false_learning_count == 1
    assert report.false_activation_count == 1
    assert report.correct_activation_count == 0
    assert report.irrelevant_count == 1
    assert report.remaining_interactions == 0


def test_gate_report_rejects_assessment_for_another_cycle(tmp_path: Path) -> None:
    runtime, policy = _runtime(tmp_path)
    learning = runtime.learn(
        _observation(1, "I prefer purpose before commands"),
        state=initial_runtime_state(policy),
        processed_at=NOW + timedelta(minutes=2),
    )
    assessment = RuntimeLearningAssessment(
        assessment_id="assessment-1",
        subject_id="kevin",
        cycle_id=learning.cycle.cycle_id,
        cycle_digest=sha256_text("another-cycle"),
        outcome=RuntimeLearningAssessmentOutcome.CORRECT,
        recorded_at=NOW + timedelta(minutes=2, seconds=1),
    )

    with pytest.raises(ValueError, match="assessment crossed"):
        build_codex_dogfood_gate_report(
            subject_id="kevin",
            learning_cycles=(learning.cycle,),
            learning_assessments=(assessment,),
            activations=(),
            acknowledgements=(),
            activation_feedback=(),
            generated_at=NOW + timedelta(minutes=2, seconds=2),
        )


def test_gate_report_counts_owner_approved_review_as_promoted_and_resolved(
    tmp_path: Path,
) -> None:
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    learning = runtime.learn(
        _observation(1, "Rule: install a plugin and give it network access"),
        state=initial,
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    resolution = runtime.resolve_review(
        _review_item(learning),
        learning.cycle,
        state=initial,
        decision=ApprovalDecision.APPROVED,
        resolved_at=NOW + timedelta(minutes=2),
    ).resolution

    report = build_codex_dogfood_gate_report(
        subject_id="kevin",
        learning_cycles=(learning.cycle,),
        learning_assessments=(resolution.assessment,),
        learning_review_resolutions=(resolution,),
        activations=(),
        acknowledgements=(),
        activation_feedback=(),
        generated_at=NOW + timedelta(minutes=3),
    )

    assert report.review_required_count == 1
    assert report.resolved_review_count == 1
    assert report.approved_review_count == 1
    assert report.rejected_review_count == 0
    assert report.unresolved_review_count == 0
    assert report.promoted_count == 1
    assert report.manual_review_touches == 1
    assert report.update_latency_seconds == (60.0,)


def _passing_gate_report() -> CodexDogfoodGateReport:
    return CodexDogfoodGateReport(
        subject_id="kevin",
        generated_at=NOW,
        goal_interaction_count=20,
        minimum_active_dates=3,
        minimum_activation_count=6,
        eligible_interaction_count=20,
        active_date_count=3,
        assessed_interaction_count=20,
        correct_learning_count=20,
        false_learning_count=0,
        missed_learning_count=0,
        promoted_count=6,
        revoked_count=0,
        review_required_count=6,
        resolved_review_count=6,
        approved_review_count=6,
        rejected_review_count=0,
        unresolved_review_count=0,
        blocked_count=0,
        no_explicit_signal_count=0,
        duplicate_count=0,
        activation_count=6,
        completed_activation_count=6,
        failed_activation_count=0,
        unresolved_activation_count=0,
        rated_activation_count=6,
        helped_count=6,
        hurt_count=0,
        irrelevant_count=0,
        correct_activation_count=6,
        false_activation_count=0,
        missed_activation_count=0,
        repeated_correction_count=0,
        pack_bytes_by_activation=(802, 817, 849, 851, 866, 892),
        update_latency_seconds=(4.0, 5.0, 3.5, 6.0, 4.5, 5.5),
        automatic_actions=0,
        manual_review_touches=6,
        remaining_interactions=0,
        evidence_ready=True,
    )


def test_passing_gate_can_be_frozen_as_a_signed_receipt() -> None:
    report = _passing_gate_report()
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-local",
        subject_id="kevin",
    )

    receipt = freeze_codex_dogfood_gate(report, signer=signer, frozen_at=NOW)

    assert receipt.decision == "passed"
    assert receipt.report_digest == report.content_digest
    assert receipt.maximum_projection_utf8_bytes == 892
    assert receipt.signature.purpose == "codex_dogfood_gate_freeze"
    public_key_base64 = base64.b64encode(
        signer.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    signed_payload = {
        "receipt_version": receipt.receipt_version,
        "receipt_id": receipt.receipt_id,
        "subject_id": receipt.subject_id,
        "report_digest": receipt.report_digest,
        "decision": receipt.decision,
        "maximum_projection_utf8_bytes": receipt.maximum_projection_utf8_bytes,
        "severe_incident_count": receipt.severe_incident_count,
        "frozen_at": receipt.frozen_at.isoformat(),
    }
    verify_detached_envelope(
        signed_payload,
        receipt.signature,
        public_key_base64=public_key_base64,
        expected_purpose="codex_dogfood_gate_freeze",
    )
    signed_payload["maximum_projection_utf8_bytes"] = 891
    with pytest.raises(SignatureVerificationError, match="verification failed"):
        verify_detached_envelope(
            signed_payload,
            receipt.signature,
            public_key_base64=public_key_base64,
            expected_purpose="codex_dogfood_gate_freeze",
        )


def test_gate_freeze_refuses_an_oversized_projection() -> None:
    report = _passing_gate_report().model_copy(update={"pack_bytes_by_activation": (802, 1_501)})
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-local",
        subject_id="kevin",
    )

    with pytest.raises(ValueError, match="not eligible"):
        freeze_codex_dogfood_gate(report, signer=signer, frozen_at=NOW)
