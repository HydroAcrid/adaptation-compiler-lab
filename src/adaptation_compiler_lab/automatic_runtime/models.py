"""Typed contracts for the automatic adaptation product loop.

The models in this module deliberately separate sensitive interaction text from durable runtime
receipts. Raw text is accepted by :class:`InteractionObservation`, captured into the encrypted raw
store, and then represented only by content digests and promoted behavioral clauses.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ArtifactRef,
    ArtifactRoute,
    CaptureReceiptRef,
    ConsentReceiptRef,
    EvaluationCase,
    EvaluationCaseRef,
    Evidence,
    EvidenceRef,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    PermittedUse,
    Sha256Digest,
    SourceClass,
    TaskRecordRef,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import Scope, scope_is_within, strings_are_sorted_unique
from adaptation_compiler_lab.governance import (
    CaptureReceipt,
    ConsentReceipt,
    GovernanceEvent,
    GovernanceEventType,
    SignerIdentity,
)
from adaptation_compiler_lab.runtime import ExternalGovernedRelease
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection


class AdaptationLayer(StrEnum):
    """Separately governed inputs combined by the future product runtime."""

    PERMANENT_PROFILE = "permanent_profile"
    CURRENT_CONTEXT = "current_context"
    TEMPORARY_CAPABILITY_PRESET = "temporary_capability_preset"
    PERSONAL_PRESET_OVERLAY = "personal_preset_overlay"


class FeedbackSignalKind(StrEnum):
    """Explicit user signals admitted by the deterministic first detector."""

    MEMORY = "memory"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    PROMPT_RULE = "prompt_rule"
    POSITIVE_EXAMPLE = "positive_example"
    CORRECTION = "correction"
    REVOCATION = "revocation"


class AutomationDisposition(StrEnum):
    """Outcome of one automatic-runtime cycle."""

    IGNORED_UNTRUSTED = "ignored_untrusted"
    NO_EXPLICIT_SIGNAL = "no_explicit_signal"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    PROMOTED = "promoted"
    REVOKED = "revoked"
    DUPLICATE = "duplicate"


class RuntimeTransitionKind(StrEnum):
    ADDITION = "addition"
    SCOPED_CORRECTION = "scoped_correction"
    SUPERSESSION = "supersession"
    REVOCATION = "revocation"


class RuntimeNoticeKind(StrEnum):
    LEARNED = "learned"
    UPDATED = "updated"
    REMOVED = "removed"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    IGNORED = "ignored"
    UNCHANGED = "unchanged"


class RuntimeFeedbackOutcome(StrEnum):
    HELPED = "helped"
    HURT = "hurt"
    IRRELEVANT = "irrelevant"


_AUTO_ROUTES = frozenset(
    {
        ArtifactRoute.MEMORY,
        ArtifactRoute.PREFERENCE,
        ArtifactRoute.EXAMPLE,
        ArtifactRoute.PROCEDURE,
        ArtifactRoute.PROMPT_RULE,
    }
)
_REQUIRED_USES = frozenset(
    {
        PermittedUse.AUDIT,
        PermittedUse.CONSTRUCTION,
        PermittedUse.PROMOTION,
        PermittedUse.TARGET_DELIVERY,
    }
)


class StandingAutomationPolicy(FrozenModel):
    """One signed-policy target authorizing low-risk, reversible automatic adaptation."""

    policy_id: Identifier
    policy_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    scope: Scope
    permitted_uses: tuple[PermittedUse, ...]
    allowed_routes: Annotated[tuple[ArtifactRoute, ...], Field(min_length=1)]
    allowed_target_families: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    maximum_behavior_utf8_bytes: int = Field(default=800, ge=1, le=4_000)
    retention_days: int = Field(default=30, ge=1, le=30)
    auto_activate: Literal[True] = True
    notify_on_change: Literal[True] = True
    effective_at: UtcDateTime
    expires_at: UtcDateTime

    @field_validator("permitted_uses")
    @classmethod
    def uses_are_sorted_unique(cls, value: tuple[PermittedUse, ...]) -> tuple[PermittedUse, ...]:
        raw = tuple(item.value for item in value)
        if not strings_are_sorted_unique(raw):
            raise ValueError("standing-policy uses must be sorted and unique")
        return value

    @field_validator("allowed_routes")
    @classmethod
    def routes_are_safe_and_unique(
        cls, value: tuple[ArtifactRoute, ...]
    ) -> tuple[ArtifactRoute, ...]:
        raw = tuple(item.value for item in value)
        if not strings_are_sorted_unique(raw):
            raise ValueError("standing-policy routes must be sorted and unique")
        unsupported = set(value) - _AUTO_ROUTES
        if unsupported:
            raise ValueError(
                "standing policy cannot auto-authorize skills, tools, adapters, or "
                "evaluation-only routes"
            )
        return value

    @field_validator("allowed_target_families")
    @classmethod
    def targets_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("standing-policy targets must be sorted and unique")
        return value

    @model_validator(mode="after")
    def policy_is_bounded(self) -> Self:
        if self.scope.subject_ids != (self.subject_id,):
            raise ValueError("standing policy must contain exactly its subject")
        if not set(self.permitted_uses).issuperset(_REQUIRED_USES):
            raise ValueError("standing policy lacks a required automatic-runtime use")
        if self.expires_at <= self.effective_at:
            raise ValueError("standing policy expiry must follow its effective time")
        if self.scope.target_families and not set(self.allowed_target_families) <= set(
            self.scope.target_families
        ):
            raise ValueError("standing-policy targets exceed its scope")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)

    @property
    def authorization_target_ref(self) -> str:
        return f"standing-automation-policy:{self.policy_id}"


class InteractionObservation(FrozenModel):
    """Transient user interaction supplied by a trusted host integration."""

    observation_id: Identifier
    subject_id: Identifier
    task_ref: TaskRecordRef
    turn_id: Identifier
    actor: ActorRef
    source_class: SourceClass
    text: NonEmptyStr
    scope: Scope
    observed_at: UtcDateTime
    source_system: Literal["codex_app_server", "local_interaction_runtime"]
    source_version: NonEmptyStr
    source_schema_digest: Sha256Digest
    affected_artifact_id: Identifier | None = None

    @model_validator(mode="after")
    def authority_is_not_inferred(self) -> Self:
        if self.subject_id not in self.scope.subject_ids:
            raise ValueError("interaction subject must be within its scope")
        if self.source_class is SourceClass.EXPLICIT_USER_FEEDBACK and (
            self.actor.kind is not ActorKind.USER or self.actor.actor_id != self.subject_id
        ):
            raise ValueError("explicit feedback must come from the exact subject user")
        return self

    @property
    def payload_bytes(self) -> bytes:
        return self.text.encode("utf-8")

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CapturedInteraction(FrozenModel):
    """Signed, encrypted-capture metadata for one transient interaction."""

    observation_digest: Sha256Digest
    signer_identity: SignerIdentity
    policy_authorization: GovernanceEvent
    consent: ConsentReceipt
    capture: CaptureReceipt
    evidence: Evidence

    @model_validator(mode="after")
    def references_are_exact(self) -> Self:
        if self.evidence.task_ref is None:
            raise ValueError("captured interaction evidence requires an exact task")
        if self.evidence.task_ref.record_id not in self.consent.source_selector.source_ids:
            raise ValueError("captured interaction task is outside the exact consent selector")
        return self


class DetectedFeedback(FrozenModel):
    """Raw-free deterministic interpretation of an explicit user signal."""

    candidate_id: Identifier
    observation_digest: Sha256Digest
    signal_kind: FeedbackSignalKind | None = None
    normalized_behavior: NonEmptyStr | None = None
    requested_route: ArtifactRoute | None = None
    affected_artifact_id: Identifier | None = None
    claim_key: Identifier | None = None
    scope: Scope
    layer: AdaptationLayer
    disposition: AutomationDisposition
    reasons: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    detected_at: UtcDateTime
    evaluation_required: Literal[True] = True

    @field_validator("reasons")
    @classmethod
    def reasons_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("detector reasons must be sorted and unique")
        return value

    @model_validator(mode="after")
    def detection_shape_matches_disposition(self) -> Self:
        actionable = self.disposition in {
            AutomationDisposition.PROMOTED,
            AutomationDisposition.REVIEW_REQUIRED,
            AutomationDisposition.REVOKED,
            AutomationDisposition.DUPLICATE,
        }
        if actionable != (self.signal_kind is not None):
            raise ValueError("actionable detector disposition requires one signal kind")
        if self.signal_kind is FeedbackSignalKind.REVOCATION:
            if self.affected_artifact_id is None or self.normalized_behavior is not None:
                raise ValueError("revocation must identify one artifact and contain no behavior")
        elif self.signal_kind is not None and (
            self.normalized_behavior is None
            or self.requested_route is None
            or self.claim_key is None
        ):
            raise ValueError("non-revocation signals require behavior, route, and claim key")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeEvaluationReceipt(FrozenModel):
    """Deterministic evaluation-first record created before any promotion."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    candidate_digest: Sha256Digest
    candidate_case: EvaluationCase
    approved_case: EvaluationCase | None
    checks: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    passed: bool
    review_required: bool
    evaluated_at: UtcDateTime

    @field_validator("checks")
    @classmethod
    def checks_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("runtime evaluation checks must be sorted and unique")
        return value

    @model_validator(mode="after")
    def evaluation_is_first(self) -> Self:
        if self.passed != (self.approved_case is not None and not self.review_required):
            raise ValueError("passing evaluation requires one approved non-review case")
        return self

    @property
    def approved_case_ref(self) -> EvaluationCaseRef | None:
        if self.approved_case is None:
            return None
        return EvaluationCaseRef(
            record_id=self.approved_case.record_id,
            record_version=self.approved_case.record_version,
            content_digest=canonical_digest(self.approved_case),
        )

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeLearningTransition(FrozenModel):
    """One evaluated and attributable change to the governed runtime release."""

    transition_id: Identifier
    sequence: int = Field(ge=1)
    kind: RuntimeTransitionKind
    source_layer: AdaptationLayer
    claim_key: Identifier | None = None
    source_evidence: Evidence
    consent: ConsentReceipt
    capture: CaptureReceipt
    signer_identity: SignerIdentity
    evaluation: RuntimeEvaluationReceipt
    review: Approval
    review_event: GovernanceEvent
    instruction: ArtifactRenderProjection | None = None
    affected_artifact_id: Identifier | None = None
    supersedes_artifact_ids: tuple[Identifier, ...] = ()
    released_at: UtcDateTime
    activated_at: UtcDateTime

    @field_validator("supersedes_artifact_ids")
    @classmethod
    def supersessions_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("runtime supersessions must be sorted and unique")
        return value

    @model_validator(mode="after")
    def transition_is_promotable(self) -> Self:
        if not self.evaluation.passed or self.evaluation.approved_case_ref is None:
            raise ValueError("runtime transition requires a passing evaluation-first receipt")
        if self.released_at > self.activated_at:
            raise ValueError("runtime release must precede activation")
        if (
            self.review_event.event_type is not GovernanceEventType.REVIEW_DECISION
            or self.review_event.target_ref != f"runtime-evaluation:{self.evaluation.receipt_id}"
            or self.review_event.target_digest != self.evaluation.content_digest
            or self.review_event.decision != "approved"
            or self.review_event.subject_id != self.source_evidence.created_by.actor_id
        ):
            raise ValueError("runtime review event does not authorize the exact evaluation")
        if self.source_layer in {
            AdaptationLayer.TEMPORARY_CAPABILITY_PRESET,
            AdaptationLayer.PERSONAL_PRESET_OVERLAY,
        }:
            raise ValueError("automatic feedback cannot create or modify capability presets")
        if self.kind is RuntimeTransitionKind.ADDITION:
            if (
                self.instruction is None
                or self.affected_artifact_id is not None
                or self.supersedes_artifact_ids
            ):
                raise ValueError("addition must introduce exactly one instruction")
        elif self.kind in {
            RuntimeTransitionKind.SCOPED_CORRECTION,
            RuntimeTransitionKind.SUPERSESSION,
        }:
            if (
                self.instruction is None
                or self.affected_artifact_id is None
                or self.supersedes_artifact_ids != (self.affected_artifact_id,)
            ):
                raise ValueError("correction or supersession must replace exactly one artifact")
        elif (
            self.instruction is not None
            or self.affected_artifact_id is None
            or self.supersedes_artifact_ids
        ):
            raise ValueError("revocation must remove exactly one artifact")
        if self.kind is RuntimeTransitionKind.REVOCATION:
            if self.claim_key is not None:
                raise ValueError("revocation uses its exact artifact target, not a new claim key")
        elif self.claim_key is None:
            raise ValueError("an introduced adaptation requires one stable claim key")
        return self

    @property
    def evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            record_id=self.source_evidence.record_id,
            record_version=self.source_evidence.record_version,
            content_digest=canonical_digest(self.source_evidence),
        )

    @property
    def consent_ref(self) -> ConsentReceiptRef:
        return ConsentReceiptRef(
            object_id=self.consent.receipt_id,
            content_digest=canonical_digest(self.consent),
        )

    @property
    def capture_ref(self) -> CaptureReceiptRef:
        return CaptureReceiptRef(
            object_id=self.capture.receipt_id,
            content_digest=canonical_digest(self.capture),
        )

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CapabilityPresetRef(FrozenModel):
    """Portable identity only; importing and evaluating presets belongs to Milestone 6B."""

    preset_id: Identifier
    preset_version: NonEmptyStr
    content_digest: Sha256Digest


class RuntimeLayerBinding(FrozenModel):
    """Exact layer ownership for one active artifact."""

    artifact_ref: ArtifactRef
    layer: AdaptationLayer
    capability_preset_ref: CapabilityPresetRef | None = None

    @model_validator(mode="after")
    def preset_reference_matches_layer(self) -> Self:
        preset_layer = self.layer in {
            AdaptationLayer.TEMPORARY_CAPABILITY_PRESET,
            AdaptationLayer.PERSONAL_PRESET_OVERLAY,
        }
        if preset_layer != (self.capability_preset_ref is not None):
            raise ValueError(
                "preset layers require an exact preset reference and other layers do not"
            )
        return self


class ComposedRuntimeRelease(FrozenModel):
    """Governed release plus non-target-visible ownership of each composition layer."""

    composition_version: Literal["1.0.0"] = "1.0.0"
    governed_release: ExternalGovernedRelease
    layer_bindings: tuple[RuntimeLayerBinding, ...]
    active_capability_presets: tuple[CapabilityPresetRef, ...] = ()

    @model_validator(mode="after")
    def bindings_are_exact(self) -> Self:
        artifact_refs = tuple(item.artifact_ref for item in self.governed_release.active_artifacts)
        binding_refs = tuple(item.artifact_ref for item in self.layer_bindings)
        if binding_refs != artifact_refs:
            raise ValueError("every active artifact requires one exact ordered layer binding")
        presets = tuple(
            sorted(
                self.active_capability_presets,
                key=lambda item: (item.preset_id, item.preset_version, item.content_digest),
            )
        )
        if presets != self.active_capability_presets or len(presets) != len(set(presets)):
            raise ValueError("active capability presets must be sorted and unique")
        bound_presets = {
            item.capability_preset_ref
            for item in self.layer_bindings
            if item.capability_preset_ref is not None
        }
        if bound_presets != set(self.active_capability_presets):
            raise ValueError("preset layer bindings must match the active preset set")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class AutomaticRuntimeState(FrozenModel):
    """Immutable state snapshot reproduced from its complete transition history."""

    state_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    standing_policy_digest: Sha256Digest
    generation: int = Field(ge=0)
    transitions: tuple[RuntimeLearningTransition, ...] = ()
    release: ComposedRuntimeRelease | None = None
    previous_release_digests: tuple[Sha256Digest, ...] = ()

    @model_validator(mode="after")
    def state_sequence_is_exact(self) -> Self:
        sequences = tuple(item.sequence for item in self.transitions)
        if sequences != tuple(range(1, len(self.transitions) + 1)):
            raise ValueError("runtime transitions must be contiguous and ordered")
        if self.generation != len(self.transitions):
            raise ValueError("runtime generation must equal its transition count")
        if bool(self.transitions) != (self.release is not None):
            raise ValueError("runtime release presence must match transition history")
        if not strings_are_sorted_unique(self.previous_release_digests):
            raise ValueError("previous runtime release digests must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeDeliveryReceipt(FrozenModel):
    """Raw-free exact binding for one task-scoped runtime delivery."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    task_ref: TaskRecordRef
    target_family: Identifier
    original_task_digest: Sha256Digest
    external_release_digest: Sha256Digest
    composed_release_digest: Sha256Digest
    projection_digest: Sha256Digest
    projection_manifest_digest: Sha256Digest
    material_digest: Sha256Digest
    material_utf8_bytes: int = Field(ge=0)
    delivered_task_digest: Sha256Digest
    material_occurrences: Literal[0, 1]
    delivered_at: UtcDateTime


class AutomaticRenderedMaterial(FrozenModel):
    """Codex material that may be empty after the final active rule is revoked."""

    renderer_id: Literal["codex-automatic-runtime"] = "codex-automatic-runtime"
    renderer_version: Literal["1.0.0"] = "1.0.0"
    target_family: Literal["codex"] = "codex"
    content: str
    content_digest: Sha256Digest
    utf8_bytes: int = Field(ge=0)
    clause_digests: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def material_measurement_is_exact(self) -> Self:
        from adaptation_compiler_lab.targets.base import sha256_text

        if self.content_digest != sha256_text(self.content):
            raise ValueError("automatic material digest is inconsistent")
        if self.utf8_bytes != len(self.content.encode("utf-8")):
            raise ValueError("automatic material byte count is inconsistent")
        return self


class RuntimeNotice(FrozenModel):
    """Small user-visible notification with an exact undo target where applicable."""

    notice_id: Identifier
    kind: RuntimeNoticeKind
    summary: NonEmptyStr
    transition_id: Identifier | None = None
    undo_artifact_id: Identifier | None = None
    created_at: UtcDateTime


class RuntimeCycleReceipt(FrozenModel):
    """Append-only raw-free account of one detection, evaluation, and delivery cycle."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    cycle_id: Identifier
    subject_id: Identifier
    observation_id: Identifier
    observation_digest: Sha256Digest
    prior_state_digest: Sha256Digest
    resulting_state_digest: Sha256Digest
    disposition: AutomationDisposition
    detected_feedback_digest: Sha256Digest | None = None
    evaluation_receipt_digest: Sha256Digest | None = None
    transition_digest: Sha256Digest | None = None
    release_digest: Sha256Digest | None = None
    release_event_digest: Sha256Digest | None = None
    activation_event_digest: Sha256Digest | None = None
    rendered_material_digest: Sha256Digest | None = None
    rendered_material_utf8_bytes: int = Field(default=0, ge=0)
    delivery_receipt_digest: Sha256Digest | None = None
    active_artifact_ids: tuple[Identifier, ...] = ()
    update_latency_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    automatic_actions: int = Field(default=0, ge=0)
    manual_review_touches: int = Field(default=0, ge=0)
    notice: RuntimeNotice
    created_at: UtcDateTime

    @model_validator(mode="after")
    def promoted_cycles_bind_outputs(self) -> Self:
        changed = self.disposition in {
            AutomationDisposition.PROMOTED,
            AutomationDisposition.REVOKED,
        }
        outputs = (
            self.evaluation_receipt_digest,
            self.transition_digest,
            self.release_digest,
            self.release_event_digest,
            self.activation_event_digest,
            self.rendered_material_digest,
            self.delivery_receipt_digest,
        )
        if changed and any(item is None for item in outputs):
            raise ValueError("changed runtime cycle must bind every evaluation and delivery output")
        if not changed and any(
            item is not None
            for item in (
                self.transition_digest,
                self.release_digest,
                self.release_event_digest,
                self.activation_event_digest,
                self.rendered_material_digest,
                self.delivery_receipt_digest,
            )
        ):
            raise ValueError("unchanged runtime cycle cannot claim release or delivery outputs")
        if self.active_artifact_ids != tuple(sorted(set(self.active_artifact_ids))):
            raise ValueError("cycle active artifact IDs must be sorted and unique")
        if changed and self.automatic_actions < 1:
            raise ValueError("changed runtime cycle must record automatic work")
        if (
            self.disposition is AutomationDisposition.REVIEW_REQUIRED
            and self.manual_review_touches != 0
        ):
            raise ValueError("queued review is not a completed manual review touch")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeReviewQueueItem(FrozenModel):
    """Raw-free durable handoff for an adaptation that cannot be promoted automatically."""

    queue_version: Literal["1.0.0"] = "1.0.0"
    queue_id: Identifier
    subject_id: Identifier
    cycle_id: Identifier
    detection: DetectedFeedback
    captured: CapturedInteraction
    evaluation: RuntimeEvaluationReceipt
    created_at: UtcDateTime

    @model_validator(mode="after")
    def review_bindings_are_exact(self) -> Self:
        if self.detection.disposition is not AutomationDisposition.REVIEW_REQUIRED:
            raise ValueError("review queue requires a review-required detection")
        if self.evaluation.passed or not self.evaluation.review_required:
            raise ValueError("review queue requires a non-passing review evaluation")
        if self.captured.observation_digest != self.detection.observation_digest:
            raise ValueError("review queue capture does not bind the detected observation")
        if self.evaluation.candidate_digest != self.detection.content_digest:
            raise ValueError("review queue evaluation does not bind the detection")
        if self.subject_id != self.captured.evidence.created_by.actor_id:
            raise ValueError("review queue crossed its evidence subject boundary")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PreparedRuntimeTask(FrozenModel):
    """Transient task text returned to the target host but never stored in the receipt ledger."""

    original_task: NonEmptyStr
    delivered_task: NonEmptyStr
    rendered_material: AutomaticRenderedMaterial
    receipt: RuntimeDeliveryReceipt

    @model_validator(mode="after")
    def one_material_instance_is_delivered(self) -> Self:
        material = self.rendered_material.content.rstrip()
        expected = 0 if not material else 1
        actual = 0 if not material else self.delivered_task.count(material)
        if actual != expected or self.receipt.material_occurrences != expected:
            raise ValueError("runtime material must occur exactly once in the delivered task")
        return self


class RuntimeActivationFeedback(FrozenModel):
    """Append-only helped/hurt/irrelevant feedback for one exact runtime delivery."""

    feedback_version: Literal["1.0.0"] = "1.0.0"
    feedback_id: Identifier
    subject_id: Identifier
    cycle_id: Identifier
    delivery_receipt_digest: Sha256Digest
    outcome: RuntimeFeedbackOutcome
    relevant_artifact_ids: tuple[Identifier, ...]
    activated_artifact_ids: tuple[Identifier, ...]
    correction_key: Identifier | None = None
    recorded_at: UtcDateTime

    @field_validator("relevant_artifact_ids", "activated_artifact_ids")
    @classmethod
    def artifact_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("runtime feedback artifact IDs must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class AutomaticRuntimeMetrics(FrozenModel):
    """Longitudinal product measures derived from immutable cycles and feedback."""

    cycle_count: int = Field(ge=0)
    promoted_count: int = Field(ge=0)
    revoked_count: int = Field(ge=0)
    review_queue_count: int = Field(ge=0)
    helped_count: int = Field(ge=0)
    hurt_count: int = Field(ge=0)
    irrelevant_count: int = Field(ge=0)
    repeated_correction_count: int = Field(ge=0)
    correct_activation_count: int = Field(ge=0)
    false_activation_count: int = Field(ge=0)
    missed_activation_count: int = Field(ge=0)
    pack_bytes_by_generation: tuple[int, ...]
    update_latency_seconds: tuple[float, ...]
    automatic_actions: int = Field(ge=0)
    manual_review_touches: int = Field(ge=0)


def infer_layer(scope: Scope) -> AdaptationLayer:
    """Route narrowed repository/task learning to context and broad learning to the profile."""

    context_dimensions = (
        scope.workspace_ids,
        scope.project_ids,
        scope.repository_ids,
        scope.task_classes,
        scope.environment_ids,
        scope.activation_conditions,
        scope.exclusions,
    )
    return (
        AdaptationLayer.CURRENT_CONTEXT
        if any(context_dimensions)
        else AdaptationLayer.PERMANENT_PROFILE
    )


def require_policy_scope(scope: Scope, policy: StandingAutomationPolicy) -> None:
    """Fail closed when detected learning would exceed standing authorization."""

    if not scope_is_within(scope, policy.scope):
        raise ValueError("detected adaptation scope exceeds the standing policy")
