"""Raw-free product-facing snapshot for review-mode longitudinal dogfood."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.gate import (
    CodexDogfoodGateReport,
    build_codex_dogfood_gate_report,
)
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    AdaptationLayer,
    AutomaticRuntimeState,
    FeedbackDetectorMode,
    FeedbackSignalKind,
    RuntimeNotice,
    RuntimeReviewQueueItem,
)
from adaptation_compiler_lab.domain import (
    ArtifactRoute,
    CaptureReceiptRef,
    ConsentReceiptRef,
    EvidenceRef,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Scope,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.serialization import canonical_digest

ReviewAction = Literal["approve", "reject", "refine_scope"]
AllowanceState = Literal["available", "used", "exceeded"]


class ReviewProposalCard(FrozenModel):
    """Compact proposal and exact lineage shown to the owner, never supporting raw text."""

    card_version: Literal["1.1.0"] = "1.1.0"
    review_number: int = Field(ge=1)
    queue_id: Identifier
    cycle_id: Identifier
    proposal_digest: Sha256Digest
    signal_kind: FeedbackSignalKind
    behavior: NonEmptyStr | None = None
    affected_artifact_id: Identifier | None = None
    route: ArtifactRoute | None = None
    layer: AdaptationLayer
    scope: Scope
    reasons: tuple[NonEmptyStr, ...]
    evidence_ref: EvidenceRef
    consent_ref: ConsentReceiptRef
    capture_ref: CaptureReceiptRef
    available_actions: tuple[ReviewAction, ...]
    created_at: UtcDateTime
    raw_payload_exposed: Literal[False] = False

    @model_validator(mode="after")
    def actions_and_shape_match_signal(self) -> Self:
        expected_actions: tuple[ReviewAction, ...] = (
            ("approve", "reject")
            if self.signal_kind is FeedbackSignalKind.REVOCATION
            else ("approve", "refine_scope", "reject")
        )
        if self.available_actions != expected_actions:
            raise ValueError("review proposal actions are inconsistent")
        if self.signal_kind is FeedbackSignalKind.REVOCATION:
            if (
                self.behavior is not None
                or self.route is not None
                or self.affected_artifact_id is None
            ):
                raise ValueError("review revocation card is inconsistent")
        elif self.behavior is None or self.route is None or self.affected_artifact_id is not None:
            raise ValueError("review learning card is inconsistent")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ActivationFeedbackCard(FrozenModel):
    """One completed activation waiting for helped/hurt/irrelevant owner feedback."""

    card_version: Literal["1.0.0"] = "1.0.0"
    activation_id: Identifier
    task_ref_id: Identifier
    delivery_receipt_digest: Sha256Digest
    active_artifact_ids: tuple[Identifier, ...]
    projection_utf8_bytes: int = Field(ge=0)
    activated_at: UtcDateTime
    completed_at: UtcDateTime
    available_actions: tuple[Literal["helped", "hurt", "irrelevant"], ...] = (
        "helped",
        "hurt",
        "irrelevant",
    )
    raw_payload_exposed: Literal[False] = False


class ReviewModeDogfoodMetrics(FrozenModel):
    """Product-friction measures not already represented by the frozen 6A.2C gate."""

    resolved_review_count: int = Field(ge=0)
    scope_refinement_count: int = Field(ge=0)
    pending_review_count: int = Field(ge=0)
    pending_feedback_count: int = Field(ge=0)
    review_decision_latency_seconds: tuple[float, ...]
    pending_review_age_seconds: tuple[float, ...]
    activation_feedback_latency_seconds: tuple[float, ...]


class ReviewModeDogfoodSnapshot(FrozenModel):
    """Single actionable daily view over the governed automatic-runtime ledgers."""

    snapshot_version: Literal["1.1.0"] = "1.1.0"
    working_product_name: Literal["Temper"] = "Temper"
    naming_status: Literal["internal_working_name"] = "internal_working_name"
    subject_id: Identifier
    generated_at: UtcDateTime
    detector_mode: FeedbackDetectorMode
    automatic_promotion_enabled: Literal[False] = False
    credential_enrolled: bool
    watcher_active: bool
    generation: int = Field(ge=0)
    active_artifact_count: int = Field(ge=0)
    proposals: tuple[ReviewProposalCard, ...]
    activation_feedback: tuple[ActivationFeedbackCard, ...]
    recent_notices: tuple[RuntimeNotice, ...]
    metrics: ReviewModeDogfoodMetrics
    gate: CodexDogfoodGateReport
    next_actions: tuple[NonEmptyStr, ...]
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def action_counts_are_exact(self) -> Self:
        if self.metrics.pending_review_count != len(self.proposals):
            raise ValueError("dogfood snapshot pending review count is inconsistent")
        if self.metrics.pending_feedback_count != len(self.activation_feedback):
            raise ValueError("dogfood snapshot pending feedback count is inconsistent")
        if not self.next_actions:
            raise ValueError("dogfood snapshot must state the next product action")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ActiveAdaptationCard(FrozenModel):
    """Raw-free behavior and governance summary for one active artifact."""

    card_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: Identifier
    artifact_version: NonEmptyStr
    artifact_type: NonEmptyStr
    layer: AdaptationLayer
    intent: NonEmptyStr
    required_behaviors: tuple[NonEmptyStr, ...]
    scope: Scope
    evidence_count: int = Field(ge=1)
    review_at: UtcDateTime | None = None
    expires_at: UtcDateTime | None = None
    raw_payload_exposed: Literal[False] = False


class GateAllowanceCard(FrozenModel):
    """One frozen error allowance rendered without implying that readiness means success."""

    name: Literal["missed_learning", "false_learning", "false_activation"]
    observed: int = Field(ge=0)
    maximum: Literal[1] = 1
    state: AllowanceState

    @model_validator(mode="after")
    def state_matches_count(self) -> Self:
        expected: AllowanceState = (
            "available" if self.observed == 0 else "used" if self.observed == 1 else "exceeded"
        )
        if self.state != expected:
            raise ValueError("gate allowance state is inconsistent")
        return self


class TerminalAlphaSnapshot(FrozenModel):
    """Typed raw-free source for terminal, plain-text, and JSON product views."""

    snapshot_version: Literal["1.1.0"] = "1.1.0"
    review_mode: ReviewModeDogfoodSnapshot
    configured_project_ids: tuple[Identifier, ...]
    active_adaptations: tuple[ActiveAdaptationCard, ...]
    allowances: tuple[GateAllowanceCard, GateAllowanceCard, GateAllowanceCard]
    latest_delivered_projection_utf8_bytes: int = Field(ge=0)
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def state_is_consistent(self) -> Self:
        if self.configured_project_ids != tuple(sorted(set(self.configured_project_ids))):
            raise ValueError("terminal project IDs must be sorted and unique")
        if self.review_mode.active_artifact_count != len(self.active_adaptations):
            raise ValueError("terminal active-adaptation count is inconsistent")
        expected_names = ("missed_learning", "false_learning", "false_activation")
        if tuple(item.name for item in self.allowances) != expected_names:
            raise ValueError("terminal gate allowances are not in canonical order")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def review_proposal_card(
    item: RuntimeReviewQueueItem,
    *,
    review_number: int,
) -> ReviewProposalCard:
    """Project one immutable queue item into a compact owner-facing card."""

    detection = item.detection
    signal = detection.signal_kind
    if signal is None:
        raise ValueError("review proposal requires one explicit feedback signal")
    evidence = item.captured.evidence
    return ReviewProposalCard(
        review_number=review_number,
        queue_id=item.queue_id,
        cycle_id=item.cycle_id,
        proposal_digest=detection.content_digest,
        signal_kind=signal,
        behavior=detection.normalized_behavior,
        affected_artifact_id=detection.affected_artifact_id,
        route=detection.requested_route,
        layer=detection.layer,
        scope=detection.scope,
        reasons=detection.reasons,
        evidence_ref=EvidenceRef(
            record_id=evidence.record_id,
            record_version=evidence.record_version,
            content_digest=canonical_digest(evidence),
        ),
        consent_ref=ConsentReceiptRef(
            object_id=item.captured.consent.receipt_id,
            content_digest=canonical_digest(item.captured.consent),
        ),
        capture_ref=CaptureReceiptRef(
            object_id=item.captured.capture.receipt_id,
            content_digest=canonical_digest(item.captured.capture),
        ),
        available_actions=(
            ("approve", "reject")
            if signal is FeedbackSignalKind.REVOCATION
            else ("approve", "refine_scope", "reject")
        ),
        created_at=item.created_at,
    )


def build_review_mode_dogfood_snapshot(
    ledger: AutomaticRuntimeLedger,
    *,
    subject_id: Identifier,
    generated_at: datetime,
    detector_mode: FeedbackDetectorMode,
    credential_enrolled: bool,
    watcher_active: bool,
) -> ReviewModeDogfoodSnapshot:
    """Build one deterministic raw-free action view from append-only runtime state."""

    state = ledger.current()
    if state is None or state.subject_id != subject_id:
        raise ValueError("dogfood snapshot requires an initialized subject ledger")
    cycles = ledger.learning_cycles()
    assessments = ledger.learning_assessments()
    resolutions = ledger.learning_review_resolutions()
    activations = ledger.activations()
    acknowledgements = ledger.delivery_acknowledgements()
    feedback = ledger.feedback()
    gate = build_codex_dogfood_gate_report(
        subject_id=subject_id,
        learning_cycles=cycles,
        learning_assessments=assessments,
        activations=activations,
        acknowledgements=acknowledgements,
        activation_feedback=feedback,
        learning_review_resolutions=resolutions,
        learning_review_items=ledger.learning_review_items(),
        generated_at=generated_at,
    )
    all_review_items = ledger.learning_review_items()
    review_number_by_queue = {
        item.queue_id: number for number, item in enumerate(all_review_items, start=1)
    }
    unresolved_review_items = ledger.unresolved_learning_review_items()
    proposals = tuple(
        review_proposal_card(
            item,
            review_number=review_number_by_queue[item.queue_id],
        )
        for item in unresolved_review_items
    )
    feedback_by_activation = {item.cycle_id: item for item in feedback}
    activation_by_id = {item.activation_id: item for item in activations}
    pending_activation_feedback = tuple(
        ActivationFeedbackCard(
            activation_id=acknowledgement.activation_id,
            task_ref_id=activation_by_id[acknowledgement.activation_id].task_ref.record_id,
            delivery_receipt_digest=activation_by_id[
                acknowledgement.activation_id
            ].delivery_receipt_digest,
            active_artifact_ids=activation_by_id[acknowledgement.activation_id].active_artifact_ids,
            projection_utf8_bytes=activation_by_id[
                acknowledgement.activation_id
            ].material_utf8_bytes,
            activated_at=activation_by_id[acknowledgement.activation_id].activated_at,
            completed_at=acknowledgement.acknowledged_at,
        )
        for acknowledgement in acknowledgements
        if acknowledgement.status == "completed"
        and acknowledgement.activation_id not in feedback_by_activation
    )
    cycle_by_id = {item.cycle_id: item for item in cycles}
    feedback_latency = tuple(
        (item.recorded_at - activation_by_id[item.cycle_id].activated_at).total_seconds()
        for item in feedback
        if item.cycle_id in activation_by_id
    )
    review_latency = tuple(
        (item.resolved_at - cycle_by_id[item.cycle_id].created_at).total_seconds()
        for item in resolutions
    )
    pending_review_age = tuple(
        (generated_at - item.created_at).total_seconds() for item in unresolved_review_items
    )
    if any(value < 0 for value in (*feedback_latency, *review_latency, *pending_review_age)):
        raise ValueError("dogfood snapshot cannot predate its source receipts")
    next_actions: list[str] = []
    if proposals:
        next_actions.append(f"Review {len(proposals)} proposed adaptation(s).")
    if pending_activation_feedback:
        next_actions.append(
            f"Rate {len(pending_activation_feedback)} completed activation(s) "
            "as helped, hurt, or irrelevant."
        )
    if not credential_enrolled:
        next_actions.append("Restore local credential enrollment before changing state.")
    if not watcher_active:
        next_actions.append("The watcher is inactive; run `temper poll` after ordinary work.")
    if not next_actions:
        next_actions.append("Continue normal work; no owner action is pending.")
    active_artifact_count = (
        0 if state.release is None else len(state.release.governed_release.active_artifacts)
    )
    return ReviewModeDogfoodSnapshot(
        subject_id=subject_id,
        generated_at=generated_at,
        detector_mode=detector_mode,
        credential_enrolled=credential_enrolled,
        watcher_active=watcher_active,
        generation=state.generation,
        active_artifact_count=active_artifact_count,
        proposals=proposals,
        activation_feedback=pending_activation_feedback,
        recent_notices=tuple(item.notice for item in cycles[-10:]),
        metrics=ReviewModeDogfoodMetrics(
            resolved_review_count=len(resolutions),
            scope_refinement_count=sum(item.scope_refinement is not None for item in resolutions),
            pending_review_count=len(proposals),
            pending_feedback_count=len(pending_activation_feedback),
            review_decision_latency_seconds=review_latency,
            pending_review_age_seconds=pending_review_age,
            activation_feedback_latency_seconds=feedback_latency,
        ),
        gate=gate,
        next_actions=tuple(next_actions),
    )


def build_terminal_alpha_snapshot(
    review_mode: ReviewModeDogfoodSnapshot,
    *,
    state: AutomaticRuntimeState,
    configured_project_ids: tuple[Identifier, ...],
) -> TerminalAlphaSnapshot:
    """Build the complete presentation snapshot from already-governed runtime state."""

    artifacts = () if state.release is None else state.release.governed_release.active_artifacts
    layer_by_artifact = (
        {}
        if state.release is None
        else {item.artifact_ref.record_id: item.layer for item in state.release.layer_bindings}
    )
    active = tuple(
        ActiveAdaptationCard(
            artifact_id=item.artifact_ref.record_id,
            artifact_version=item.artifact_ref.record_version,
            artifact_type=item.artifact_type.value,
            layer=layer_by_artifact[item.artifact_ref.record_id],
            intent=item.behavioral_contract.intent,
            required_behaviors=item.behavioral_contract.required_behaviors,
            scope=item.scope,
            evidence_count=len(item.evidence_links.supporting),
            review_at=item.review_at,
            expires_at=item.expires_at,
        )
        for item in artifacts
    )
    gate = review_mode.gate

    def allowance(
        name: Literal["missed_learning", "false_learning", "false_activation"],
        observed: int,
    ) -> GateAllowanceCard:
        state_value: AllowanceState = (
            "available" if observed == 0 else "used" if observed == 1 else "exceeded"
        )
        return GateAllowanceCard(name=name, observed=observed, state=state_value)

    return TerminalAlphaSnapshot(
        review_mode=review_mode,
        configured_project_ids=tuple(sorted(configured_project_ids)),
        active_adaptations=active,
        allowances=(
            allowance("missed_learning", gate.missed_learning_count),
            allowance("false_learning", gate.false_learning_count),
            allowance("false_activation", gate.false_activation_count),
        ),
        latest_delivered_projection_utf8_bytes=(
            0 if not gate.pack_bytes_by_activation else gate.pack_bytes_by_activation[-1]
        ),
    )
