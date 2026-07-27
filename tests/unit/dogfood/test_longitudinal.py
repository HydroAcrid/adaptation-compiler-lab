from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.dogfood import (
    ActivationFeedback,
    DogfoodContext,
    DogfoodFeedbackLedger,
    DogfoodFeedbackOutcome,
    DogfoodTransition,
    DogfoodTransitionKind,
    DogfoodWorkflowError,
    LongitudinalDogfoodCompiler,
    LongitudinalDogfoodResult,
    deliver_stage_pack,
    instructions_for_context,
    summarize_feedback,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ApprovalDecision,
    ArtifactKind,
    ArtifactRef,
    AuthorityClass,
    BehavioralContract,
    CaptureReceiptRef,
    ClaimAuthority,
    ClaimAuthoritySet,
    ClaimType,
    EvaluationCaseRef,
    Evidence,
    EvidenceLinks,
    EvidenceRef,
    EvidenceState,
    Partition,
    PayloadReference,
    PermittedUse,
    PrivacyContext,
    PrivacyReviewState,
    RedactionState,
    Scope,
    SensitivityClass,
    SourceClass,
    TaskRecordRef,
)
from adaptation_compiler_lab.governance import SignerIdentity, SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    governance_ref,
    sign_capture,
    sign_consent,
)
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.serialization import canonical_digest, record_ref
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    TargetKind,
)
from adaptation_compiler_lab.targets.profiles import default_target_profile

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)
SUBJECT = "dogfood-user"
USER = ActorRef(actor_id=SUBJECT, kind=ActorKind.USER)
USES = (
    PermittedUse.CONSTRUCTION,
    PermittedUse.PROMOTION,
    PermittedUse.TARGET_DELIVERY,
)


def _digest(label: str) -> str:
    return canonical_digest({"label": label})


def _signer() -> tuple[GovernanceSigner, SignerIdentity]:
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    signer = GovernanceSigner(key, identity_id="dogfood-signer", subject_id=SUBJECT)
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CONSENT,),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=90),
    )
    return signer, identity


def _privacy() -> PrivacyContext:
    return PrivacyContext(
        sensitivity=SensitivityClass.INTERNAL,
        consent_basis="dogfood-consent",
        permitted_uses=USES,
        review_state=PrivacyReviewState.APPROVED,
        reviewed_by=USER,
        reviewed_at=NOW,
    )


def _instruction(
    *,
    artifact_id: str,
    evidence: Evidence,
    evaluation: EvaluationCaseRef,
    behavior: str,
    scope: Scope,
    priority: int,
) -> ArtifactRenderProjection:
    evidence_ref = cast(EvidenceRef, record_ref(evidence))
    return ArtifactRenderProjection(
        artifact_ref=ArtifactRef(
            record_id=artifact_id,
            record_version="1.0.0",
            content_digest=_digest(artifact_id),
        ),
        artifact_type=ArtifactKind.PROMPT_RULE,
        behavioral_contract=BehavioralContract(
            intent=f"Apply {artifact_id}",
            required_behaviors=(behavior,),
            verification_requirements=("Verify the selected publish action before completion.",),
        ),
        scope=scope,
        evidence_links=EvidenceLinks(supporting=(evidence_ref,)),
        evaluation_cases=(evaluation,),
        claim_authorities=ClaimAuthoritySet(
            entries=(
                ClaimAuthority(
                    claim_type=ClaimType.USER_CORRECTION,
                    authority_class=AuthorityClass.USER_NORMATIVE,
                    evidence_refs=(evidence_ref,),
                ),
            )
        ),
        privacy=_privacy(),
        precedence=priority,
        target_compatibility=("codex-file-surfaces",),
        source_partitions=(Partition.CONSTRUCTION,),
    )


def _transition(
    stage: int,
    kind: DogfoodTransitionKind,
    *,
    artifact_id: str | None,
    affected: str | None = None,
) -> DogfoodTransition:
    signer, identity = _signer()
    observed_at = NOW + timedelta(hours=stage)
    source_id = f"dogfood-feedback-{stage}"
    consent = sign_consent(
        {
            "receipt_id": f"dogfood-consent-{stage}",
            "subject_id": SUBJECT,
            "source_selector": {
                "source_system": "codex_app_server",
                "selection_method": "explicit_task_ids",
                "source_ids": [source_id],
            },
            "scope": {"subject_ids": [SUBJECT]},
            "permitted_uses": [item.value for item in USES],
            "issued_at": (observed_at - timedelta(minutes=5)).isoformat(),
            "expires_at": (observed_at + timedelta(days=30)).isoformat(),
            "retention_until": (observed_at + timedelta(days=30)).isoformat(),
            "policy_version": "1.0.0",
        },
        signer,
    )
    capture = sign_capture(
        {
            "receipt_id": f"dogfood-capture-{stage}",
            "subject_id": SUBJECT,
            "consent_ref": governance_ref(consent).model_dump(mode="json"),
            "source_selector": consent.source_selector.model_dump(mode="json"),
            "source_version": "dogfood-fixture-v1",
            "source_schema_digest": _digest("source-schema"),
            "payload_digest": _digest(source_id),
            "captured_at": observed_at.isoformat(),
            "synthetic": False,
        },
        signer,
    )
    evidence = Evidence(
        record_id=f"dogfood-evidence-{stage}",
        schema_version="1.1",
        record_version="1.0.0",
        created_at=observed_at,
        created_by=USER,
        policy_version="1.0.0",
        observed_at=observed_at,
        producer=USER,
        source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
        authority_class=AuthorityClass.USER_NORMATIVE,
        authority_reason="Explicit public dogfood feedback.",
        allowed_claim_types=(ClaimType.USER_CORRECTION,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator=f"sha256/dogfood/{stage}",
            content_digest=_digest(source_id),
            media_type="text/plain",
            byte_length=64,
        ),
        task_ref=TaskRecordRef(record_id=source_id, record_version="1.0.0"),
        consent_receipt_ref=governance_ref(consent),
        capture_receipt_ref=governance_ref(capture),
        scope=Scope(subject_ids=(SUBJECT,)),
        privacy=PrivacyContext(
            sensitivity=SensitivityClass.INTERNAL,
            consent_basis=consent.receipt_id,
            permitted_uses=USES,
        ),
        partition=Partition.CONSTRUCTION,
    )
    evaluation = EvaluationCaseRef(
        record_id=f"dogfood-evaluation-{stage}",
        record_version="1.0.0",
        content_digest=_digest(f"evaluation-{stage}"),
    )
    scopes = {
        1: Scope(subject_ids=(SUBJECT,), target_families=(TargetKind.CODEX.value,)),
        2: Scope(
            subject_ids=(SUBJECT,),
            project_ids=("generated-cache",),
            target_families=(TargetKind.CODEX.value,),
        ),
        3: Scope(subject_ids=(SUBJECT,), target_families=(TargetKind.CODEX.value,)),
    }
    behaviors = {
        1: (
            "For persistent user-managed destinations, create a recoverable backup before "
            "replacing existing content."
        ),
        2: (
            "For disposable generated-cache destinations, atomically replace existing content "
            "without creating a backup."
        ),
        3: (
            "For persistent user-managed destinations, refuse overwrite unless a recoverable "
            "backup is explicitly requested."
        ),
    }
    instruction = (
        None
        if artifact_id is None
        else _instruction(
            artifact_id=artifact_id,
            evidence=evidence,
            evaluation=evaluation,
            behavior=behaviors[stage],
            scope=scopes[stage],
            priority=20 if stage == 2 else 10,
        )
    )
    review_time = observed_at + timedelta(seconds=20)
    return DogfoodTransition(
        transition_id=f"dogfood-transition-{stage}",
        stage=stage,
        kind=kind,
        source_evidence=evidence,
        consent=consent,
        capture=capture,
        signer_identity=identity,
        evaluation_case_ref=evaluation,
        review=Approval(
            decision=ApprovalDecision.APPROVED,
            approver=USER,
            decided_at=review_time,
            policy_version="1.0.0",
            rationale="Approve the explicit dogfood behavior.",
        ),
        instruction=instruction,
        affected_artifact_id=affected,
        supersedes_artifact_ids=(
            () if affected is None or kind is DogfoodTransitionKind.REVOCATION else (affected,)
        ),
        workflow_started_at=observed_at + timedelta(seconds=10),
        released_at=observed_at + timedelta(seconds=30),
        activated_at=observed_at + timedelta(seconds=40),
        maintenance_actions=stage + 2,
    )


def _dogfood() -> LongitudinalDogfoodResult:
    transitions = (
        _transition(1, DogfoodTransitionKind.ADDITION, artifact_id="persistent-backup"),
        _transition(
            2,
            DogfoodTransitionKind.SCOPED_CORRECTION,
            artifact_id="disposable-atomic-replace",
            affected="persistent-backup",
        ),
        _transition(
            3,
            DogfoodTransitionKind.SUPERSESSION,
            artifact_id="persistent-refuse-default",
            affected="persistent-backup",
        ),
    )
    return LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )


def _context(project_id: str) -> DogfoodContext:
    return DogfoodContext(
        subject_id=SUBJECT,
        target_family=TargetKind.CODEX.value,
        project_id=project_id,
        evaluated_at=NOW + timedelta(days=1),
    )


def test_three_stage_compilation_scopes_supersedes_and_removes() -> None:
    result = _dogfood()

    assert [
        tuple(item.artifact_ref.record_id for item in stage.active_instructions)
        for stage in result.stages
    ] == [
        ("persistent-backup",),
        ("disposable-atomic-replace", "persistent-backup"),
        ("disposable-atomic-replace", "persistent-refuse-default"),
    ]
    assert tuple(
        item.artifact_ref.record_id
        for item in instructions_for_context(result.stages[1], _context("customer-project"))
    ) == ("persistent-backup",)
    assert tuple(
        item.artifact_ref.record_id
        for item in instructions_for_context(result.stages[1], _context("generated-cache"))
    ) == ("disposable-atomic-replace",)
    assert tuple(
        item.artifact_ref.record_id
        for item in instructions_for_context(result.stages[2], _context("customer-project"))
    ) == ("persistent-refuse-default",)
    assert tuple(
        item.artifact_ref.record_id
        for item in instructions_for_context(result.stages[2], _context("generated-cache"))
    ) == ("disposable-atomic-replace",)
    assert result.stages[2].revoked_artifact_ids == ("persistent-backup",)
    final_agents = next(
        item.content for item in result.stages[2].rendered_pack.files if item.path == "AGENTS.md"
    )
    assert "persistent-backup" not in final_agents
    assert "dogfood-evidence-1" not in final_agents


def test_stage_three_revocation_removes_broad_rule_without_scope_leakage() -> None:
    result = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        (
            _transition(
                1,
                DogfoodTransitionKind.ADDITION,
                artifact_id="persistent-backup",
            ),
            _transition(
                2,
                DogfoodTransitionKind.SCOPED_CORRECTION,
                artifact_id="disposable-atomic-replace",
                affected="persistent-backup",
            ),
            _transition(
                3,
                DogfoodTransitionKind.REVOCATION,
                artifact_id=None,
                affected="persistent-backup",
            ),
        )
    )
    final = result.stages[2]

    assert tuple(item.artifact_ref.record_id for item in final.active_instructions) == (
        "disposable-atomic-replace",
    )
    assert not instructions_for_context(final, _context("customer-project"))
    assert tuple(
        item.artifact_ref.record_id
        for item in instructions_for_context(final, _context("generated-cache"))
    ) == ("disposable-atomic-replace",)
    final_agents = next(
        item.content for item in final.rendered_pack.files if item.path == "AGENTS.md"
    )
    assert "persistent-backup" not in final_agents
    assert "dogfood-evidence-1" not in final_agents


def test_instructions_do_not_activate_for_unrelated_subject_or_target() -> None:
    result = _dogfood()
    wrong_subject = DogfoodContext(
        subject_id="different-user",
        target_family=TargetKind.CODEX.value,
        project_id="generated-cache",
        evaluated_at=NOW + timedelta(days=1),
    )
    wrong_target = DogfoodContext(
        subject_id=SUBJECT,
        target_family=TargetKind.CLAUDE_CODE.value,
        project_id="generated-cache",
        evaluated_at=NOW + timedelta(days=1),
    )

    for stage in result.stages:
        assert not instructions_for_context(stage, wrong_subject)
        assert not instructions_for_context(stage, wrong_target)


def test_every_active_instruction_has_consent_capture_and_evidence_lineage() -> None:
    result = _dogfood()

    for stage in result.stages:
        assert len(stage.lineages) == len(stage.active_instructions)
        for lineage in stage.lineages:
            assert isinstance(
                lineage.consent_ref,
                type(
                    governance_ref(
                        _transition(
                            1,
                            DogfoodTransitionKind.ADDITION,
                            artifact_id="temporary-artifact",
                        ).consent
                    )
                ),
            )
            assert isinstance(lineage.capture_ref, CaptureReceiptRef)
            assert lineage.evidence_ref.content_digest.startswith("sha256:")


def test_pack_measurements_and_clean_delivery_are_deterministic(tmp_path: Path) -> None:
    first = _dogfood()
    second = _dogfood()

    assert first == second
    assert all(stage.measurement.target_visible_bytes > 0 for stage in first.stages)
    assert first.stages[1].measurement.byte_growth_from_previous > 0
    destination = tmp_path / "fresh-codex-workspace"
    receipt = deliver_stage_pack(first.stages[2], destination)

    assert not receipt.codex_session_started
    assert receipt.provider_billed_calls == 0
    assert receipt.pack_digest == first.stages[2].rendered_pack.pack_digest
    assert "AGENTS.md" in receipt.written_relative_paths


def test_invalid_signature_fails_closed() -> None:
    transition = _transition(
        1,
        DogfoodTransitionKind.ADDITION,
        artifact_id="persistent-backup",
    )
    tampered = transition.model_copy(
        update={"consent": transition.consent.model_copy(update={"policy_version": "9.9.9"})}
    )

    with pytest.raises(DogfoodWorkflowError, match="verification failed"):
        LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
            (
                tampered,
                _transition(
                    2,
                    DogfoodTransitionKind.SCOPED_CORRECTION,
                    artifact_id="disposable-atomic-replace",
                    affected="persistent-backup",
                ),
                _transition(
                    3,
                    DogfoodTransitionKind.SUPERSESSION,
                    artifact_id="persistent-refuse-default",
                    affected="persistent-backup",
                ),
            )
        )


def test_capture_payload_binds_exact_evidence() -> None:
    first = _transition(
        1,
        DogfoodTransitionKind.ADDITION,
        artifact_id="persistent-backup",
    )
    payload = cast(PayloadReference, first.source_evidence.payload)
    substituted = first.model_copy(
        update={
            "source_evidence": first.source_evidence.model_copy(
                update={
                    "payload": payload.model_copy(
                        update={"content_digest": _digest("substituted-payload")}
                    )
                }
            )
        }
    )

    with pytest.raises(DogfoodWorkflowError, match="signed capture digest"):
        LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
            (
                substituted,
                _transition(
                    2,
                    DogfoodTransitionKind.SCOPED_CORRECTION,
                    artifact_id="disposable-atomic-replace",
                    affected="persistent-backup",
                ),
                _transition(
                    3,
                    DogfoodTransitionKind.SUPERSESSION,
                    artifact_id="persistent-refuse-default",
                    affected="persistent-backup",
                ),
            )
        )


def test_feedback_ledger_and_metrics_record_activation_quality(tmp_path: Path) -> None:
    result = _dogfood()
    database = tmp_path / "dogfood.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    ledger = DogfoodFeedbackLedger(database, subject_id=SUBJECT)
    feedback = (
        ActivationFeedback(
            feedback_id="feedback-1",
            subject_id=SUBJECT,
            stage=1,
            task_id="task-1",
            pack_digest=result.stages[0].rendered_pack.pack_digest,
            outcome=DogfoodFeedbackOutcome.HELPED,
            relevant_instruction_ids=("persistent-backup",),
            activated_instruction_ids=("persistent-backup",),
            recorded_at=NOW + timedelta(days=1),
            recorded_by=SUBJECT,
        ),
        ActivationFeedback(
            feedback_id="feedback-2",
            subject_id=SUBJECT,
            stage=2,
            task_id="task-2",
            pack_digest=result.stages[1].rendered_pack.pack_digest,
            outcome=DogfoodFeedbackOutcome.HURT,
            relevant_instruction_ids=("disposable-atomic-replace",),
            activated_instruction_ids=("persistent-backup",),
            correction_key="publish-policy",
            correction_required=True,
            recorded_at=NOW + timedelta(days=2),
            recorded_by=SUBJECT,
        ),
        ActivationFeedback(
            feedback_id="feedback-3",
            subject_id=SUBJECT,
            stage=3,
            task_id="task-3",
            pack_digest=result.stages[2].rendered_pack.pack_digest,
            outcome=DogfoodFeedbackOutcome.IRRELEVANT,
            relevant_instruction_ids=(),
            activated_instruction_ids=(),
            correction_key="publish-policy",
            correction_required=True,
            recorded_at=NOW + timedelta(days=3),
            recorded_by=SUBJECT,
        ),
    )
    for item in feedback:
        assert ledger.add(item)
        assert not ledger.add(item)
    with pytest.raises(ValueError, match="subject boundary"):
        ledger.add(
            feedback[0].model_copy(
                update={"feedback_id": "feedback-other-subject", "subject_id": "different-user"}
            )
        )

    metrics = summarize_feedback(ledger.list(), result)

    assert metrics.feedback_count == 3
    assert metrics.helped_count == metrics.hurt_count == metrics.irrelevant_count == 1
    assert metrics.repeated_correction_count == 1
    assert metrics.correct_activation_count == 2
    assert metrics.false_activation_count == 1
    assert metrics.missed_activation_count == 1
    assert metrics.total_maintenance_actions == 12
