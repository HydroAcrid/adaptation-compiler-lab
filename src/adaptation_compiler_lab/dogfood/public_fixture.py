"""Deterministic synthetic inputs for the public longitudinal engineering fixture."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.dogfood.models import (
    DogfoodTransition,
    DogfoodTransitionKind,
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
from adaptation_compiler_lab.serialization import canonical_digest, record_ref
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    TargetKind,
)

PUBLIC_DOGFOOD_NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)
PUBLIC_DOGFOOD_SUBJECT = "dogfood-user"
_USER = ActorRef(actor_id=PUBLIC_DOGFOOD_SUBJECT, kind=ActorKind.USER)
_USES = (
    PermittedUse.CONSTRUCTION,
    PermittedUse.PROMOTION,
    PermittedUse.TARGET_DELIVERY,
)


def _digest(label: str) -> str:
    return canonical_digest({"label": label})


def _signer() -> tuple[GovernanceSigner, SignerIdentity]:
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    signer = GovernanceSigner(
        key,
        identity_id="dogfood-signer",
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
    )
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CONSENT,),
        created_at=PUBLIC_DOGFOOD_NOW - timedelta(days=1),
        expires_at=PUBLIC_DOGFOOD_NOW + timedelta(days=90),
    )
    return signer, identity


def _privacy() -> PrivacyContext:
    return PrivacyContext(
        sensitivity=SensitivityClass.INTERNAL,
        consent_basis="dogfood-consent",
        permitted_uses=_USES,
        review_state=PrivacyReviewState.APPROVED,
        reviewed_by=_USER,
        reviewed_at=PUBLIC_DOGFOOD_NOW,
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
    observed_at = PUBLIC_DOGFOOD_NOW + timedelta(hours=stage)
    source_id = f"dogfood-feedback-{stage}"
    consent = sign_consent(
        {
            "receipt_id": f"dogfood-consent-{stage}",
            "subject_id": PUBLIC_DOGFOOD_SUBJECT,
            "source_selector": {
                "source_system": "codex_app_server",
                "selection_method": "explicit_task_ids",
                "source_ids": [source_id],
            },
            "scope": {"subject_ids": [PUBLIC_DOGFOOD_SUBJECT]},
            "permitted_uses": [item.value for item in _USES],
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
            "subject_id": PUBLIC_DOGFOOD_SUBJECT,
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
        created_by=_USER,
        policy_version="1.0.0",
        observed_at=observed_at,
        producer=_USER,
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
        scope=Scope(subject_ids=(PUBLIC_DOGFOOD_SUBJECT,)),
        privacy=PrivacyContext(
            sensitivity=SensitivityClass.INTERNAL,
            consent_basis=consent.receipt_id,
            permitted_uses=_USES,
        ),
        partition=Partition.CONSTRUCTION,
    )
    evaluation = EvaluationCaseRef(
        record_id=f"dogfood-evaluation-{stage}",
        record_version="1.0.0",
        content_digest=_digest(f"evaluation-{stage}"),
    )
    scopes = {
        1: Scope(
            subject_ids=(PUBLIC_DOGFOOD_SUBJECT,),
            target_families=(TargetKind.CODEX.value,),
        ),
        2: Scope(
            subject_ids=(PUBLIC_DOGFOOD_SUBJECT,),
            project_ids=("generated-cache",),
            target_families=(TargetKind.CODEX.value,),
        ),
        3: Scope(
            subject_ids=(PUBLIC_DOGFOOD_SUBJECT,),
            target_families=(TargetKind.CODEX.value,),
        ),
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
            approver=_USER,
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


def public_dogfood_transitions() -> tuple[
    DogfoodTransition,
    DogfoodTransition,
    DogfoodTransition,
]:
    """Return the immutable synthetic three-stage 6A engineering sequence."""

    return (
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
            DogfoodTransitionKind.SUPERSESSION,
            artifact_id="persistent-refuse-default",
            affected="persistent-backup",
        ),
    )
