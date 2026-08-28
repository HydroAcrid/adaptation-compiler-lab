"""Automatic capture, evaluation, compilation, activation, delivery, and undo service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from adaptation_compiler_lab.automatic_runtime.compiler import (
    compile_runtime_release,
    compile_runtime_releases,
)
from adaptation_compiler_lab.automatic_runtime.detector import (
    detect_explicit_feedback,
    detect_feedback,
)
from adaptation_compiler_lab.automatic_runtime.models import (
    AdaptationLayer,
    AutomaticRenderedMaterial,
    AutomaticRuntimeState,
    AutomationDisposition,
    CapturedInteraction,
    ComposedRuntimeRelease,
    DetectedFeedback,
    FeedbackDetectorMode,
    FeedbackSignalKind,
    InteractionObservation,
    PreparedRuntimeActivation,
    PreparedRuntimeTask,
    RuntimeCycleReceipt,
    RuntimeDeliveryReceipt,
    RuntimeEvaluationReceipt,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeLearningCycleReceipt,
    RuntimeLearningReviewResolution,
    RuntimeLearningTransition,
    RuntimeNotice,
    RuntimeNoticeKind,
    RuntimeReviewQueueItem,
    RuntimeReviewScopeRefinement,
    RuntimeTaskActivationReceipt,
    RuntimeTransitionKind,
    SemanticFeedbackInterpretation,
    StandingAutomationPolicy,
    infer_layer,
    require_policy_scope,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ApprovalDecision,
    ArtifactKind,
    ArtifactRef,
    ArtifactRoute,
    AuthorityClass,
    BehavioralContract,
    ClaimAuthority,
    ClaimAuthoritySet,
    ClaimType,
    EnvironmentSnapshot,
    EvaluationCase,
    EvaluationCaseKind,
    EvaluationCaseState,
    EvaluationSetup,
    Evidence,
    EvidenceLinks,
    EvidenceRef,
    EvidenceState,
    Partition,
    PayloadReference,
    PrivacyContext,
    PrivacyReviewState,
    RedactionState,
    Scope,
    ScoringRule,
    ScoringType,
    SensitivityClass,
    SourceClass,
    TaskRecordRef,
)
from adaptation_compiler_lab.governance import (
    GovernanceEvent,
    GovernanceEventType,
    SignerIdentity,
    SourceSelector,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    governance_ref,
    sign_capture,
    sign_consent,
    sign_governance_event,
    verify_signed_governance,
)
from adaptation_compiler_lab.instruction_environment.models import (
    InstructionEnvironmentSnapshotV1,
    InstructionRelationV1,
)
from adaptation_compiler_lab.instruction_environment.resolver import (
    apply_instruction_environment,
    bind_instruction_delta_manifest,
    build_instruction_delta_plan,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from adaptation_compiler_lab.runtime import (
    CanonicalRuntimeProjection,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
    build_runtime_projection,
)
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.codex_runtime import (
    build_runtime_projection_manifest,
    render_codex_runtime_projection,
)
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection, TargetKind


class AutomaticRuntimeError(ValueError):
    """The automatic runtime refused an unsafe, unauthorized, or incoherent operation."""


@dataclass(frozen=True, slots=True)
class AutomaticRuntimeResult:
    """Complete in-memory result; only raw-free receipts are persisted."""

    state: AutomaticRuntimeState
    cycle: RuntimeCycleReceipt
    detection: DetectedFeedback
    captured: CapturedInteraction | None = None
    evaluation: RuntimeEvaluationReceipt | None = None
    release: ComposedRuntimeRelease | None = None
    projection: CanonicalRuntimeProjection | None = None
    projection_manifest: RuntimeProjectionManifest | None = None
    prepared_task: PreparedRuntimeTask | None = None
    release_event: GovernanceEvent | None = None
    activation_event: GovernanceEvent | None = None


@dataclass(frozen=True, slots=True)
class AutomaticLearningResult:
    """Learning-only result produced after a persisted Codex interaction."""

    state: AutomaticRuntimeState
    cycle: RuntimeLearningCycleReceipt
    detection: DetectedFeedback
    captured: CapturedInteraction | None = None
    evaluation: RuntimeEvaluationReceipt | None = None
    release: ComposedRuntimeRelease | None = None
    release_event: GovernanceEvent | None = None


@dataclass(frozen=True, slots=True)
class AutomaticReviewResolutionResult:
    """Owner resolution plus the exact resulting governed state."""

    state: AutomaticRuntimeState
    resolution: RuntimeLearningReviewResolution
    release_event: GovernanceEvent | None = None


_ROUTE_TO_KIND = {
    ArtifactRoute.MEMORY: ArtifactKind.MEMORY,
    ArtifactRoute.PREFERENCE: ArtifactKind.PREFERENCE,
    ArtifactRoute.EXAMPLE: ArtifactKind.EXAMPLE,
    ArtifactRoute.PROCEDURE: ArtifactKind.PROCEDURE,
    ArtifactRoute.PROMPT_RULE: ArtifactKind.PROMPT_RULE,
}
_LAYER_PRECEDENCE = {
    AdaptationLayer.PERMANENT_PROFILE: 200,
    AdaptationLayer.CURRENT_CONTEXT: 300,
}


def initial_runtime_state(policy: StandingAutomationPolicy) -> AutomaticRuntimeState:
    """Create the empty state bound to one exact standing policy."""

    return AutomaticRuntimeState(
        subject_id=policy.subject_id,
        standing_policy_digest=policy.state_binding_digest,
        generation=0,
    )


class AutomaticAdaptationRuntime:
    """One-shot product loop intended to be called by a trusted local host integration."""

    def __init__(
        self,
        *,
        policy: StandingAutomationPolicy,
        policy_authorization: GovernanceEvent,
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
        raw_store: LocalRawPayloadStore,
        synthetic_capture: bool = False,
    ) -> None:
        if not raw_store.encrypted:
            raise AutomaticRuntimeError("automatic runtime requires encrypted raw storage")
        if (
            signer.subject_id != policy.subject_id
            or signer_identity.subject_id != policy.subject_id
            or signer.identity_id != signer_identity.identity_id
            or signer.fingerprint != signer_identity.key_fingerprint
        ):
            raise AutomaticRuntimeError("automatic runtime identity crossed its subject boundary")
        self._policy = policy
        self._authorization = policy_authorization
        self._signer = signer
        self._identity = signer_identity
        self._raw_store = raw_store
        self._synthetic_capture = synthetic_capture
        self._verify_policy(policy.effective_at)

    @staticmethod
    def _projected_artifact_ids(projection: CanonicalRuntimeProjection) -> tuple[str, ...]:
        """Return only artifacts that contributed to the target-visible projection."""

        return tuple(
            sorted(
                {
                    source.record_id
                    for clause in projection.clauses
                    for source in clause.source_artifact_refs
                }
            )
        )

    def learn(
        self,
        observation: InteractionObservation,
        *,
        state: AutomaticRuntimeState,
        processed_at: datetime,
        detector_mode: FeedbackDetectorMode = FeedbackDetectorMode.GRAMMAR,
        semantic_interpretation: SemanticFeedbackInterpretation | None = None,
    ) -> AutomaticLearningResult:
        """Capture and release eligible learning without claiming target delivery."""

        if processed_at.tzinfo is None or processed_at.utcoffset() is None:
            raise AutomaticRuntimeError("processed_at must be timezone-aware")
        if processed_at < observation.observed_at:
            raise AutomaticRuntimeError("automatic processing cannot predate the interaction")
        self._verify_policy(processed_at)
        self._validate_state(state)
        detection = detect_feedback(
            observation,
            self._policy,
            state,
            mode=detector_mode,
            semantic_interpretation=semantic_interpretation,
        )

        if detection.disposition in {
            AutomationDisposition.IGNORED_UNTRUSTED,
            AutomationDisposition.NO_EXPLICIT_SIGNAL,
            AutomationDisposition.BLOCKED,
            AutomationDisposition.DUPLICATE,
        }:
            notice = self._notice(detection, processed_at)
            cycle = RuntimeLearningCycleReceipt(
                cycle_id=f"learning-cycle-{observation.observation_id}",
                subject_id=observation.subject_id,
                observation_id=observation.observation_id,
                observation_digest=observation.content_digest,
                prior_state_digest=state.content_digest,
                resulting_state_digest=state.content_digest,
                disposition=detection.disposition,
                detected_feedback_digest=detection.content_digest,
                automatic_actions=1,
                notice=notice,
                created_at=processed_at,
            )
            return AutomaticLearningResult(
                state=state,
                cycle=cycle,
                detection=detection,
            )

        captured = self._capture(observation, detection, processed_at)
        evaluation = self._evaluate(
            detection,
            captured,
            state=state,
            processed_at=processed_at,
        )
        if not evaluation.passed:
            review_detection = detection.model_copy(
                update={"disposition": AutomationDisposition.REVIEW_REQUIRED}
            )
            notice = self._notice(review_detection, processed_at)
            cycle = RuntimeLearningCycleReceipt(
                cycle_id=f"learning-cycle-{observation.observation_id}",
                subject_id=observation.subject_id,
                observation_id=observation.observation_id,
                observation_digest=observation.content_digest,
                prior_state_digest=state.content_digest,
                resulting_state_digest=state.content_digest,
                disposition=AutomationDisposition.REVIEW_REQUIRED,
                detected_feedback_digest=detection.content_digest,
                evaluation_receipt_digest=evaluation.content_digest,
                update_latency_seconds=(processed_at - observation.observed_at).total_seconds(),
                automatic_actions=3,
                notice=notice,
                created_at=processed_at,
            )
            return AutomaticLearningResult(
                state=state,
                cycle=cycle,
                detection=detection,
                captured=captured,
                evaluation=evaluation,
            )

        transition = self._transition(
            detection,
            captured,
            evaluation,
            state=state,
            processed_at=processed_at,
        )
        transitions = (*state.transitions, transition)
        release = compile_runtime_release(transitions, subject_id=state.subject_id)
        prior_releases = compile_runtime_releases(state.transitions, subject_id=state.subject_id)
        new_state = AutomaticRuntimeState(
            subject_id=state.subject_id,
            standing_policy_digest=state.standing_policy_digest,
            generation=len(transitions),
            transitions=transitions,
            release=release,
            previous_release_digests=tuple(
                sorted({item.content_digest for item in prior_releases})
            ),
        )
        release_event = self._governance_event(
            event_id=f"runtime-release-event-{observation.observation_id}",
            event_type=GovernanceEventType.RELEASE_DECISION,
            target_ref=f"composed-runtime-release:{release.governed_release.release_ref.record_id}",
            target_digest=release.content_digest,
            decision="released",
            reason="Automatically release evaluated low-risk learning under the standing policy.",
            occurred_at=processed_at,
        )
        notice = self._notice(detection, processed_at, transition=transition)
        cycle = RuntimeLearningCycleReceipt(
            cycle_id=f"learning-cycle-{observation.observation_id}",
            subject_id=observation.subject_id,
            observation_id=observation.observation_id,
            observation_digest=observation.content_digest,
            prior_state_digest=state.content_digest,
            resulting_state_digest=new_state.content_digest,
            disposition=detection.disposition,
            detected_feedback_digest=detection.content_digest,
            evaluation_receipt_digest=evaluation.content_digest,
            transition_digest=transition.content_digest,
            release_digest=release.content_digest,
            release_event_digest=canonical_digest(release_event),
            active_artifact_ids=tuple(
                item.artifact_ref.record_id for item in release.governed_release.active_artifacts
            ),
            update_latency_seconds=(processed_at - observation.observed_at).total_seconds(),
            automatic_actions=5,
            notice=notice,
            created_at=processed_at,
        )
        return AutomaticLearningResult(
            state=new_state,
            cycle=cycle,
            detection=detection,
            captured=captured,
            evaluation=evaluation,
            release=release,
            release_event=release_event,
        )

    def resolve_review(
        self,
        review_item: RuntimeReviewQueueItem,
        cycle: RuntimeLearningCycleReceipt,
        *,
        state: AutomaticRuntimeState,
        decision: ApprovalDecision,
        resolved_at: datetime,
        refined_scope: Scope | None = None,
    ) -> AutomaticReviewResolutionResult:
        """Resolve one inactive proposal, optionally approving an exact narrower scope."""

        if resolved_at.tzinfo is None or resolved_at.utcoffset() is None:
            raise AutomaticRuntimeError("review resolution time must be timezone-aware")
        self._verify_policy(resolved_at)
        self._validate_state(state)
        if (
            review_item.subject_id != state.subject_id
            or review_item.cycle_id != cycle.cycle_id
            or cycle.subject_id != state.subject_id
            or cycle.disposition is not AutomationDisposition.REVIEW_REQUIRED
            or cycle.detected_feedback_digest != review_item.detection.content_digest
            or cycle.evaluation_receipt_digest != review_item.evaluation.content_digest
            or cycle.observation_digest != review_item.captured.observation_digest
        ):
            raise AutomaticRuntimeError("review resolution does not bind the exact queued cycle")
        if refined_scope is not None:
            if decision is not ApprovalDecision.APPROVED:
                raise AutomaticRuntimeError("only an approved review may refine proposal scope")
            if review_item.detection.signal_kind is FeedbackSignalKind.REVOCATION:
                raise AutomaticRuntimeError("revocation scope cannot be partially refined")
            if refined_scope == review_item.detection.scope:
                raise AutomaticRuntimeError("refined scope must differ from the proposal scope")
            if not self._scope_equal_or_narrower(refined_scope, review_item.detection.scope):
                raise AutomaticRuntimeError("review refinement cannot widen proposal scope")
            require_policy_scope(refined_scope, self._policy)
        review = Approval(
            decision=decision,
            approver=self._user_actor,
            decided_at=resolved_at,
            policy_version=self._policy.policy_version,
            rationale=(
                (
                    "The owner approved an exact narrower scope for the immutable proposal "
                    "after local review."
                    if refined_scope is not None
                    else "The owner approved the exact normalized proposal after local review."
                )
                if decision is ApprovalDecision.APPROVED
                else "The owner rejected the exact normalized proposal after local review."
            ),
        )
        assessment = RuntimeLearningAssessment(
            assessment_id=f"learning-assessment-{cycle.cycle_id}",
            subject_id=state.subject_id,
            cycle_id=cycle.cycle_id,
            cycle_digest=cycle.content_digest,
            outcome=(
                RuntimeLearningAssessmentOutcome.CORRECT
                if decision is ApprovalDecision.APPROVED
                else RuntimeLearningAssessmentOutcome.FALSE_POSITIVE
            ),
            recorded_at=resolved_at,
        )

        if decision is ApprovalDecision.REJECTED:
            review_event = self._governance_event(
                event_id=f"runtime-manual-review-event-{review_item.detection.candidate_id}",
                event_type=GovernanceEventType.REVIEW_DECISION,
                target_ref=f"runtime-review-queue:{review_item.queue_id}",
                target_digest=review_item.content_digest,
                decision=decision.value,
                reason="Reject the exact inactive proposal after owner review.",
                occurred_at=resolved_at,
            )
            resolution = RuntimeLearningReviewResolution(
                resolution_id=f"runtime-review-resolution-{review_item.queue_id}",
                queue_id=review_item.queue_id,
                queue_digest=review_item.content_digest,
                subject_id=state.subject_id,
                cycle_id=cycle.cycle_id,
                cycle_digest=cycle.content_digest,
                decision=decision,
                review=review,
                review_event=review_event,
                assessment=assessment,
                prior_state_digest=state.content_digest,
                resulting_state_digest=state.content_digest,
                resolved_at=resolved_at,
            )
            return AutomaticReviewResolutionResult(state=state, resolution=resolution)

        promoted_detection = review_item.detection
        scope_refinement = None
        candidate = review_item.evaluation.candidate_case
        if refined_scope is not None:
            promoted_detection = review_item.detection.model_copy(
                update={
                    "scope": refined_scope,
                    "layer": infer_layer(refined_scope),
                }
            )
            refined_evaluation = self._evaluate(
                promoted_detection,
                review_item.captured,
                state=state,
                processed_at=resolved_at,
            )
            candidate = refined_evaluation.candidate_case
            scope_refinement = RuntimeReviewScopeRefinement(
                refinement_id=f"runtime-review-refinement-{review_item.queue_id}",
                queue_id=review_item.queue_id,
                queue_digest=review_item.content_digest,
                original_detection_digest=review_item.detection.content_digest,
                refined_detection_digest=promoted_detection.content_digest,
                original_scope=review_item.detection.scope,
                refined_scope=refined_scope,
                refined_layer=promoted_detection.layer,
                refined_at=resolved_at,
            )
        approved_case = EvaluationCase.model_validate(
            {
                **candidate.model_dump(mode="python"),
                "record_version": "1.1.0",
                "created_at": resolved_at,
                "state": EvaluationCaseState.APPROVED,
                "review": review,
            }
        )
        evaluation = RuntimeEvaluationReceipt(
            receipt_id=f"runtime-reviewed-evaluation-{review_item.detection.candidate_id}",
            candidate_digest=promoted_detection.content_digest,
            candidate_case=candidate,
            approved_case=approved_case,
            checks=tuple(
                sorted(
                    {
                        *review_item.evaluation.checks,
                        (
                            "Owner approved an exact narrower proposal scope after local review."
                            if scope_refinement is not None
                            else "Owner approved the exact normalized proposal after local review."
                        ),
                    }
                )
            ),
            passed=True,
            review_required=False,
            evaluated_at=resolved_at,
        )
        review_event = self._governance_event(
            event_id=f"runtime-manual-review-event-{review_item.detection.candidate_id}",
            event_type=GovernanceEventType.REVIEW_DECISION,
            target_ref=f"runtime-evaluation:{evaluation.receipt_id}",
            target_digest=evaluation.content_digest,
            decision=decision.value,
            reason="Approve the exact normalized proposal after owner review.",
            occurred_at=resolved_at,
        )
        transition = self._transition(
            promoted_detection,
            review_item.captured,
            evaluation,
            state=state,
            processed_at=resolved_at,
            review=review,
            review_event=review_event,
        )
        transitions = (*state.transitions, transition)
        release = compile_runtime_release(transitions, subject_id=state.subject_id)
        prior_releases = compile_runtime_releases(state.transitions, subject_id=state.subject_id)
        new_state = AutomaticRuntimeState(
            subject_id=state.subject_id,
            standing_policy_digest=state.standing_policy_digest,
            generation=len(transitions),
            transitions=transitions,
            release=release,
            previous_release_digests=tuple(
                sorted({item.content_digest for item in prior_releases})
            ),
        )
        release_event = self._governance_event(
            event_id=f"runtime-reviewed-release-event-{review_item.detection.candidate_id}",
            event_type=GovernanceEventType.RELEASE_DECISION,
            target_ref=f"composed-runtime-release:{release.governed_release.release_ref.record_id}",
            target_digest=release.content_digest,
            decision="released",
            reason="Release the exact owner-approved proposal after deterministic gates pass.",
            occurred_at=resolved_at,
        )
        resolution = RuntimeLearningReviewResolution(
            resolution_version=("1.1.0" if scope_refinement is not None else "1.0.0"),
            resolution_id=f"runtime-review-resolution-{review_item.queue_id}",
            queue_id=review_item.queue_id,
            queue_digest=review_item.content_digest,
            subject_id=state.subject_id,
            cycle_id=cycle.cycle_id,
            cycle_digest=cycle.content_digest,
            decision=decision,
            review=review,
            review_event=review_event,
            assessment=assessment,
            prior_state_digest=state.content_digest,
            resulting_state_digest=new_state.content_digest,
            evaluation_digest=evaluation.content_digest,
            transition_digest=transition.content_digest,
            release_digest=release.content_digest,
            release_event_digest=canonical_digest(release_event),
            scope_refinement=scope_refinement,
            resolved_at=resolved_at,
        )
        return AutomaticReviewResolutionResult(
            state=new_state,
            resolution=resolution,
            release_event=release_event,
        )

    def activate(
        self,
        *,
        activation_id: str,
        task_ref: TaskRecordRef,
        state: AutomaticRuntimeState,
        context: RuntimeProjectionContext,
        target_task: str,
        activated_at: datetime,
        instruction_environment: InstructionEnvironmentSnapshotV1 | None = None,
        instruction_relations: tuple[InstructionRelationV1, ...] = (),
    ) -> PreparedRuntimeActivation:
        """Prepare a later task from current state and sign its separate activation."""

        if not activation_id.strip():
            raise AutomaticRuntimeError("runtime activation ID must not be empty")
        if activated_at.tzinfo is None or activated_at.utcoffset() is None:
            raise AutomaticRuntimeError("activated_at must be timezone-aware")
        self._verify_policy(activated_at)
        self._validate_state(state)
        self._validate_context(context, subject_id=state.subject_id)
        if state.release is None:
            raise AutomaticRuntimeError("runtime activation requires a governed release")
        projection = build_runtime_projection(state.release.governed_release, context)
        delta_plan = None
        if instruction_environment is not None:
            delta_plan = build_instruction_delta_plan(
                projection,
                instruction_environment,
                semantic_relations=instruction_relations,
            )
            projection = apply_instruction_environment(projection, delta_plan)
        elif instruction_relations:
            raise AutomaticRuntimeError(
                "native semantic relations require an instruction environment"
            )
        rendered, manifest = self._render(state.release, projection)
        if delta_plan is not None:
            manifest = bind_instruction_delta_manifest(manifest, delta_plan)
        prepared = self._deliver(
            task_ref=task_ref,
            receipt_id=f"runtime-delivery-{activation_id}",
            release=state.release,
            projection=projection,
            manifest=manifest,
            rendered=rendered,
            target_task=target_task,
            delivered_at=activated_at,
        )
        activation_event = self._governance_event(
            event_id=f"runtime-activation-event-{activation_id}",
            event_type=GovernanceEventType.ACTIVATION_DECISION,
            target_ref=f"runtime-delivery:{prepared.receipt.receipt_id}",
            target_digest=canonical_digest(prepared.receipt),
            decision="activated",
            reason="Activate the exact scoped projection for the next Codex task.",
            occurred_at=activated_at,
        )
        activation = RuntimeTaskActivationReceipt(
            activation_id=activation_id,
            subject_id=state.subject_id,
            task_ref=task_ref,
            state_digest=state.content_digest,
            external_release_digest=state.release.governed_release.content_digest,
            composed_release_digest=state.release.content_digest,
            projection_context_digest=canonical_digest(context),
            delivery_receipt_digest=canonical_digest(prepared.receipt),
            activation_event_digest=canonical_digest(activation_event),
            active_artifact_ids=self._projected_artifact_ids(projection),
            material_utf8_bytes=prepared.receipt.material_utf8_bytes,
            activated_at=activated_at,
        )
        return PreparedRuntimeActivation(
            task=prepared,
            activation=activation,
            activation_event=activation_event,
        )

    def prepare_task(
        self,
        observation: InteractionObservation,
        *,
        state: AutomaticRuntimeState,
        context: RuntimeProjectionContext,
        target_task: str,
        delivered_at: datetime,
    ) -> PreparedRuntimeTask:
        """Reproduce one exact scoped delivery from a durable runtime state.

        Trusted hosts use this after a crash between durable append and an idempotent delivery
        acknowledgement. The result is deterministic for the same state, context, task, and time.
        """

        if delivered_at.tzinfo is None or delivered_at.utcoffset() is None:
            raise AutomaticRuntimeError("delivered_at must be timezone-aware")
        if delivered_at < observation.observed_at:
            raise AutomaticRuntimeError("runtime delivery cannot predate the interaction")
        self._verify_policy(delivered_at)
        self._validate_state(state)
        self._validate_context(context, subject_id=observation.subject_id)
        if state.release is None:
            raise AutomaticRuntimeError("runtime delivery requires a governed release")
        projection = build_runtime_projection(state.release.governed_release, context)
        rendered, manifest = self._render(state.release, projection)
        return self._deliver(
            task_ref=observation.task_ref,
            receipt_id=f"runtime-delivery-{observation.observation_id}",
            release=state.release,
            projection=projection,
            manifest=manifest,
            rendered=rendered,
            target_task=target_task,
            delivered_at=delivered_at,
        )

    def process(
        self,
        observation: InteractionObservation,
        *,
        state: AutomaticRuntimeState,
        context: RuntimeProjectionContext,
        target_task: str,
        processed_at: datetime,
    ) -> AutomaticRuntimeResult:
        """Run detection through exact-once target delivery, or return a safe no-change cycle."""

        if processed_at.tzinfo is None or processed_at.utcoffset() is None:
            raise AutomaticRuntimeError("processed_at must be timezone-aware")
        if processed_at < observation.observed_at:
            raise AutomaticRuntimeError("automatic processing cannot predate the interaction")
        self._verify_policy(processed_at)
        self._validate_state(state)
        self._validate_context(context, subject_id=observation.subject_id)
        detection = detect_explicit_feedback(observation, self._policy, state)

        if detection.disposition in {
            AutomationDisposition.IGNORED_UNTRUSTED,
            AutomationDisposition.NO_EXPLICIT_SIGNAL,
            AutomationDisposition.BLOCKED,
            AutomationDisposition.DUPLICATE,
        }:
            notice = self._notice(detection, processed_at)
            cycle = self._unchanged_cycle(
                observation=observation,
                state=state,
                detection=detection,
                notice=notice,
                processed_at=processed_at,
            )
            return AutomaticRuntimeResult(
                state=state,
                cycle=cycle,
                detection=detection,
            )

        captured = self._capture(observation, detection, processed_at)
        evaluation = self._evaluate(
            detection,
            captured,
            state=state,
            processed_at=processed_at,
        )
        if not evaluation.passed:
            notice = self._notice(
                detection.model_copy(update={"disposition": AutomationDisposition.REVIEW_REQUIRED}),
                processed_at,
            )
            cycle = RuntimeCycleReceipt(
                cycle_id=f"cycle-{observation.observation_id}",
                subject_id=observation.subject_id,
                observation_id=observation.observation_id,
                observation_digest=observation.content_digest,
                prior_state_digest=state.content_digest,
                resulting_state_digest=state.content_digest,
                disposition=AutomationDisposition.REVIEW_REQUIRED,
                detected_feedback_digest=detection.content_digest,
                evaluation_receipt_digest=evaluation.content_digest,
                update_latency_seconds=(processed_at - observation.observed_at).total_seconds(),
                automatic_actions=3,
                notice=notice,
                created_at=processed_at,
            )
            return AutomaticRuntimeResult(
                state=state,
                cycle=cycle,
                detection=detection,
                captured=captured,
                evaluation=evaluation,
            )

        transition = self._transition(
            detection,
            captured,
            evaluation,
            state=state,
            processed_at=processed_at,
        )
        transitions = (*state.transitions, transition)
        release = compile_runtime_release(transitions, subject_id=state.subject_id)
        prior_releases = compile_runtime_releases(state.transitions, subject_id=state.subject_id)
        new_state = AutomaticRuntimeState(
            subject_id=state.subject_id,
            standing_policy_digest=state.standing_policy_digest,
            generation=len(transitions),
            transitions=transitions,
            release=release,
            previous_release_digests=tuple(
                sorted({item.content_digest for item in prior_releases})
            ),
        )
        projection = build_runtime_projection(release.governed_release, context)
        rendered, manifest = self._render(release, projection)
        prepared = self._deliver(
            task_ref=observation.task_ref,
            receipt_id=f"runtime-delivery-{observation.observation_id}",
            release=release,
            projection=projection,
            manifest=manifest,
            rendered=rendered,
            target_task=target_task,
            delivered_at=processed_at,
        )
        release_event = self._governance_event(
            event_id=f"runtime-release-event-{observation.observation_id}",
            event_type=GovernanceEventType.RELEASE_DECISION,
            target_ref=f"composed-runtime-release:{release.governed_release.release_ref.record_id}",
            target_digest=release.content_digest,
            decision="released",
            reason="Automatically release evaluated low-risk learning under the standing policy.",
            occurred_at=processed_at,
        )
        activation_event = self._governance_event(
            event_id=f"runtime-activation-event-{observation.observation_id}",
            event_type=GovernanceEventType.ACTIVATION_DECISION,
            target_ref=f"runtime-delivery:{prepared.receipt.receipt_id}",
            target_digest=canonical_digest(prepared.receipt),
            decision="activated",
            reason="Activate the exact scoped projection for the current target task.",
            occurred_at=processed_at,
        )
        notice = self._notice(detection, processed_at, transition=transition)
        cycle = RuntimeCycleReceipt(
            cycle_id=f"cycle-{observation.observation_id}",
            subject_id=observation.subject_id,
            observation_id=observation.observation_id,
            observation_digest=observation.content_digest,
            prior_state_digest=state.content_digest,
            resulting_state_digest=new_state.content_digest,
            disposition=detection.disposition,
            detected_feedback_digest=detection.content_digest,
            evaluation_receipt_digest=evaluation.content_digest,
            transition_digest=transition.content_digest,
            release_digest=release.content_digest,
            release_event_digest=canonical_digest(release_event),
            activation_event_digest=canonical_digest(activation_event),
            rendered_material_digest=rendered.content_digest,
            rendered_material_utf8_bytes=rendered.utf8_bytes,
            delivery_receipt_digest=canonical_digest(prepared.receipt),
            active_artifact_ids=self._projected_artifact_ids(projection),
            update_latency_seconds=(processed_at - observation.observed_at).total_seconds(),
            automatic_actions=6,
            notice=notice,
            created_at=processed_at,
        )
        return AutomaticRuntimeResult(
            state=new_state,
            cycle=cycle,
            detection=detection,
            captured=captured,
            evaluation=evaluation,
            release=release,
            projection=projection,
            projection_manifest=manifest,
            prepared_task=prepared,
            release_event=release_event,
            activation_event=activation_event,
        )

    def _verify_policy(self, effective_at: datetime) -> None:
        try:
            verify_signed_governance(
                self._authorization,
                self._identity,
                effective_at=effective_at,
            )
        except ValueError as error:
            raise AutomaticRuntimeError("standing-policy authorization is invalid") from error
        event = self._authorization
        if (
            event.event_type is not GovernanceEventType.ACTIVATION_DECISION
            or event.subject_id != self._policy.subject_id
            or event.target_ref != self._policy.authorization_target_ref
            or event.target_digest != self._policy.content_digest
            or event.decision != "enabled"
            or event.policy_version != self._policy.policy_version
        ):
            raise AutomaticRuntimeError(
                "signed authorization does not enable the exact standing policy"
            )
        if effective_at < self._policy.effective_at or effective_at >= self._policy.expires_at:
            raise AutomaticRuntimeError("standing policy is not active")

    def _validate_state(self, state: AutomaticRuntimeState) -> None:
        if (
            state.subject_id != self._policy.subject_id
            or state.standing_policy_digest != self._policy.state_binding_digest
        ):
            raise AutomaticRuntimeError("runtime state is bound to another policy or subject")
        if state.transitions:
            expected = compile_runtime_release(
                state.transitions,
                subject_id=state.subject_id,
            )
            if state.release != expected:
                raise AutomaticRuntimeError("runtime state release cannot be reproduced")

    def _validate_context(
        self,
        context: RuntimeProjectionContext,
        *,
        subject_id: str,
    ) -> None:
        if context.subject_id != subject_id:
            raise AutomaticRuntimeError("runtime context crossed its subject boundary")
        if context.target_family not in self._policy.allowed_target_families:
            raise AutomaticRuntimeError("target family is outside the standing policy")
        if context.target_family != TargetKind.CODEX.value:
            raise AutomaticRuntimeError("this milestone implements only the Codex delivery adapter")

    def _capture(
        self,
        observation: InteractionObservation,
        detection: DetectedFeedback,
        processed_at: datetime,
    ) -> CapturedInteraction:
        selector = SourceSelector(
            source_system=(
                "synthetic_fixture" if self._synthetic_capture else observation.source_system
            ),
            selection_method=(
                "synthetic_fixture" if self._synthetic_capture else "explicit_task_ids"
            ),
            source_ids=(observation.task_ref.record_id,),
        )
        expires_at = min(
            self._policy.expires_at,
            observation.observed_at + timedelta(days=self._policy.retention_days),
        )
        consent = sign_consent(
            {
                "receipt_id": f"runtime-consent-{observation.observation_id}",
                "subject_id": observation.subject_id,
                "source_selector": selector.model_dump(mode="json"),
                "scope": observation.scope.model_dump(mode="json"),
                "permitted_uses": [item.value for item in self._policy.permitted_uses],
                "issued_at": observation.observed_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "retention_until": expires_at.isoformat(),
                "policy_version": self._policy.policy_version,
            },
            self._signer,
        )
        reference = self._raw_store.reference_for(
            observation.payload_bytes,
            media_type="text/plain; charset=utf-8",
        )
        existed = self._raw_store.contains(reference)
        stored = self._raw_store.put(
            observation.payload_bytes,
            media_type=reference.media_type,
        )
        try:
            capture = sign_capture(
                {
                    "receipt_id": f"runtime-capture-{observation.observation_id}",
                    "subject_id": observation.subject_id,
                    "consent_ref": governance_ref(consent).model_dump(mode="json"),
                    "source_selector": selector.model_dump(mode="json"),
                    "source_version": observation.source_version,
                    "source_schema_digest": observation.source_schema_digest,
                    "payload_digest": f"sha256:{stored.sha256}",
                    "captured_at": observation.observed_at.isoformat(),
                    "synthetic": self._synthetic_capture,
                },
                self._signer,
            )
            evidence = Evidence(
                record_id=f"runtime-evidence-{observation.observation_id}",
                schema_version="1.1",
                record_version="1.0.0",
                created_at=observation.observed_at,
                created_by=observation.actor,
                policy_version=self._policy.policy_version,
                observed_at=observation.observed_at,
                producer=observation.actor,
                source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
                authority_class=AuthorityClass.USER_NORMATIVE,
                authority_reason="Explicit user feedback captured under a signed standing policy.",
                allowed_claim_types=self._claim_types(detection),
                state=EvidenceState.RAW,
                redaction_state=RedactionState.NONE,
                payload=PayloadReference(
                    locator=stored.relative_path,
                    content_digest=f"sha256:{stored.sha256}",
                    media_type=stored.media_type,
                    byte_length=stored.size_bytes,
                ),
                task_ref=observation.task_ref,
                consent_receipt_ref=governance_ref(consent),
                capture_receipt_ref=governance_ref(capture),
                scope=observation.scope,
                privacy=self._approved_privacy(
                    consent.receipt_id,
                    observation.actor,
                    processed_at,
                ),
                partition=Partition.CONSTRUCTION,
            )
        except BaseException:
            if not existed:
                self._raw_store.discard(stored)
            raise
        return CapturedInteraction(
            observation_digest=observation.content_digest,
            signer_identity=self._identity,
            policy_authorization=self._authorization,
            consent=consent,
            capture=capture,
            evidence=evidence,
        )

    def _evaluate(
        self,
        detection: DetectedFeedback,
        captured: CapturedInteraction,
        *,
        state: AutomaticRuntimeState,
        processed_at: datetime,
    ) -> RuntimeEvaluationReceipt:
        evidence = captured.evidence
        evidence_ref = self._evidence_ref(evidence)
        expected = (
            f"Remove active artifact {detection.affected_artifact_id}."
            if detection.signal_kind is FeedbackSignalKind.REVOCATION
            else cast(str, detection.normalized_behavior)
        )
        candidate = EvaluationCase(
            record_id=f"runtime-evaluation-{detection.candidate_id}",
            record_version="1.0.0",
            created_at=detection.detected_at,
            created_by=self._runtime_actor,
            policy_version=self._policy.policy_version,
            state=EvaluationCaseState.CANDIDATE,
            kind=EvaluationCaseKind.PROMOTION,
            setup=EvaluationSetup(
                instructions="Check authority, scope, safety, conflict, and lifecycle eligibility.",
                stimulus=expected,
            ),
            expected_behaviors=(expected,),
            failure_criteria=("Any automatic-promotion gate is not satisfied.",),
            scoring_rule=ScoringRule(
                scoring_type=ScoringType.OBJECTIVE,
                description="All deterministic automatic-promotion gates pass.",
                pass_threshold=1.0,
            ),
            environment=EnvironmentSnapshot(
                environment_id=(
                    evidence.scope.environment_ids[0]
                    if evidence.scope.environment_ids
                    else "automatic-runtime"
                ),
                harness_version="1.0.0",
                agent_version="automatic-runtime-1.0.0",
            ),
            scope=evidence.scope,
            source_task_ref=evidence.task_ref,
            source_evidence_refs=(evidence_ref,),
            partition=Partition.CONSTRUCTION,
            privacy=evidence.privacy,
        )
        review_required = detection.disposition is AutomationDisposition.REVIEW_REQUIRED
        if detection.signal_kind is FeedbackSignalKind.CORRECTION and not review_required:
            affected = self._active_artifact(state, detection.affected_artifact_id)
            if affected is None or not self._scope_equal_or_narrower(
                detection.scope,
                affected.scope,
            ):
                review_required = True
        checks = (
            "Capture and consent signatures bind the exact payload and subject.",
            "Correction and revocation targets are exact active artifact identifiers.",
            "Detected content contains no secret-like material.",
            "Detected route is least-invasive and standing-policy allowed.",
            "Evidence is explicit user-authored feedback with user-normative authority.",
            "Scope does not widen evidence or standing authorization.",
        )
        approved_case = None
        if not review_required:
            approval = Approval(
                decision=ApprovalDecision.APPROVED,
                approver=self._user_actor,
                decided_at=processed_at,
                policy_version=self._policy.policy_version,
                rationale=(
                    "The explicit user signal and signed standing policy authorize this "
                    "low-risk evaluation."
                ),
            )
            approved_case = EvaluationCase.model_validate(
                {
                    **candidate.model_dump(mode="python"),
                    "record_version": "1.1.0",
                    "created_at": processed_at,
                    "state": EvaluationCaseState.APPROVED,
                    "review": approval,
                }
            )
        return RuntimeEvaluationReceipt(
            receipt_id=f"runtime-evaluation-receipt-{detection.candidate_id}",
            candidate_digest=detection.content_digest,
            candidate_case=candidate,
            approved_case=approved_case,
            checks=checks,
            passed=approved_case is not None,
            review_required=review_required,
            evaluated_at=processed_at,
        )

    def _transition(
        self,
        detection: DetectedFeedback,
        captured: CapturedInteraction,
        evaluation: RuntimeEvaluationReceipt,
        *,
        state: AutomaticRuntimeState,
        processed_at: datetime,
        review: Approval | None = None,
        review_event: GovernanceEvent | None = None,
    ) -> RuntimeLearningTransition:
        sequence = state.generation + 1
        if (review is None) != (review_event is None):
            raise AutomaticRuntimeError(
                "runtime transition review inputs must be supplied together"
            )
        if review is None or review_event is None:
            review = Approval(
                decision=ApprovalDecision.APPROVED,
                approver=self._user_actor,
                decided_at=processed_at,
                policy_version=self._policy.policy_version,
                rationale=(
                    "Explicit feedback auto-promoted under the signed standing automation policy."
                ),
            )
            review_event = self._governance_event(
                event_id=f"runtime-review-event-{detection.candidate_id}",
                event_type=GovernanceEventType.REVIEW_DECISION,
                target_ref=f"runtime-evaluation:{evaluation.receipt_id}",
                target_digest=evaluation.content_digest,
                decision="approved",
                reason="Approve the exact low-risk evaluation under the standing policy.",
                occurred_at=processed_at,
            )
        instruction = None
        affected_id = detection.affected_artifact_id
        supersedes: tuple[str, ...] = ()
        if detection.signal_kind is FeedbackSignalKind.REVOCATION:
            kind = RuntimeTransitionKind.REVOCATION
        else:
            instruction = self._instruction(
                detection,
                captured,
                evaluation,
                sequence=sequence,
                state=state,
                created_at=processed_at,
            )
            if detection.signal_kind is FeedbackSignalKind.CORRECTION:
                affected = self._active_artifact(state, affected_id)
                if affected is None:
                    raise AutomaticRuntimeError("evaluated correction target is no longer active")
                kind = (
                    RuntimeTransitionKind.SUPERSESSION
                    if detection.scope == affected.scope
                    else RuntimeTransitionKind.SCOPED_CORRECTION
                )
                supersedes = (cast(str, affected_id),)
            else:
                kind = RuntimeTransitionKind.ADDITION
                affected_id = None
        return RuntimeLearningTransition(
            transition_id=f"runtime-transition-{detection.candidate_id}",
            sequence=sequence,
            kind=kind,
            source_layer=detection.layer,
            claim_key=(
                None
                if detection.signal_kind is FeedbackSignalKind.REVOCATION
                else detection.claim_key
            ),
            source_evidence=captured.evidence,
            consent=captured.consent,
            capture=captured.capture,
            signer_identity=captured.signer_identity,
            evaluation=evaluation,
            review=review,
            review_event=review_event,
            instruction=instruction,
            affected_artifact_id=affected_id,
            supersedes_artifact_ids=supersedes,
            released_at=processed_at,
            activated_at=processed_at,
        )

    def _instruction(
        self,
        detection: DetectedFeedback,
        captured: CapturedInteraction,
        evaluation: RuntimeEvaluationReceipt,
        *,
        sequence: int,
        state: AutomaticRuntimeState,
        created_at: datetime,
    ) -> ArtifactRenderProjection:
        route = cast(ArtifactRoute, detection.requested_route)
        if detection.signal_kind is FeedbackSignalKind.CORRECTION:
            affected = self._active_artifact(state, detection.affected_artifact_id)
            if affected is None:
                raise AutomaticRuntimeError("correction target vanished before promotion")
            artifact_kind = affected.artifact_type
        else:
            artifact_kind = _ROUTE_TO_KIND[route]
        behavior = cast(str, detection.normalized_behavior)
        evaluation_ref = evaluation.approved_case_ref
        if evaluation_ref is None:
            raise AutomaticRuntimeError("promoted instruction lacks an approved evaluation")
        evidence_ref = self._evidence_ref(captured.evidence)
        artifact_id = f"runtime-{cast(str, detection.claim_key)}-{sequence}"
        artifact_payload = {
            "artifact_id": artifact_id,
            "artifact_kind": artifact_kind.value,
            "behavior": behavior,
            "evidence_ref": evidence_ref.model_dump(mode="json"),
            "evaluation_ref": evaluation_ref.model_dump(mode="json"),
            "layer": detection.layer.value,
            "scope": detection.scope.model_dump(mode="json"),
        }
        claim_type = (
            ClaimType.USER_CORRECTION
            if detection.signal_kind is FeedbackSignalKind.CORRECTION
            else ClaimType.USER_PREFERENCE
        )
        return ArtifactRenderProjection(
            artifact_ref=ArtifactRef(
                record_id=artifact_id,
                record_version="1.0.0",
                content_digest=canonical_digest(artifact_payload),
            ),
            artifact_type=artifact_kind,
            behavioral_contract=BehavioralContract(
                intent=behavior,
                required_behaviors=(behavior,),
                verification_requirements=(
                    "Before finishing, check that the applicable user adaptation was followed.",
                ),
            ),
            scope=detection.scope,
            evidence_links=EvidenceLinks(
                supporting=(evidence_ref,),
                scope_limiting=(
                    (evidence_ref,) if detection.layer is AdaptationLayer.CURRENT_CONTEXT else ()
                ),
            ),
            evaluation_cases=(evaluation_ref,),
            claim_authorities=ClaimAuthoritySet(
                entries=(
                    ClaimAuthority(
                        claim_type=claim_type,
                        authority_class=AuthorityClass.USER_NORMATIVE,
                        evidence_refs=(evidence_ref,),
                    ),
                )
            ),
            privacy=self._approved_privacy(
                captured.consent.receipt_id,
                self._user_actor,
                created_at,
            ),
            precedence=_LAYER_PRECEDENCE[detection.layer],
            target_compatibility=self._policy.allowed_target_families,
            source_partitions=(Partition.CONSTRUCTION,),
        )

    @staticmethod
    def _render(
        release: ComposedRuntimeRelease,
        projection: CanonicalRuntimeProjection,
    ) -> tuple[AutomaticRenderedMaterial, RuntimeProjectionManifest]:
        if projection.clauses:
            compact = render_codex_runtime_projection(projection)
            manifest = build_runtime_projection_manifest(
                release=release.governed_release,
                projection=projection,
                rendered=compact,
            )
            return (
                AutomaticRenderedMaterial(
                    content=compact.content,
                    content_digest=compact.content_digest,
                    utf8_bytes=compact.utf8_bytes,
                    clause_digests=compact.clause_digests,
                ),
                manifest,
            )
        empty = AutomaticRenderedMaterial(
            content="",
            content_digest=sha256_text(""),
            utf8_bytes=0,
            clause_digests=(),
        )
        return (
            empty,
            RuntimeProjectionManifest(
                external_release_digest=release.governed_release.content_digest,
                runtime_projection_digest=projection.content_digest,
                target_renderer_id=empty.renderer_id,
                target_renderer_version=empty.renderer_version,
                rendered_content_digest=empty.content_digest,
                rendered_utf8_bytes=0,
                clause_bindings=(),
            ),
        )

    def _deliver(
        self,
        *,
        task_ref: TaskRecordRef,
        receipt_id: str,
        release: ComposedRuntimeRelease,
        projection: CanonicalRuntimeProjection,
        manifest: RuntimeProjectionManifest,
        rendered: AutomaticRenderedMaterial,
        target_task: str,
        delivered_at: datetime,
    ) -> PreparedRuntimeTask:
        normalized_task = target_task.strip()
        if not normalized_task:
            raise AutomaticRuntimeError("target task must not be empty")
        material = rendered.content.rstrip()
        delivered_task = (
            normalized_task
            if not material
            else (
                f"Current approved task rules (apply exactly):\n\n{material}\n\n"
                f"Task:\n\n{normalized_task}"
            )
        )
        if material and delivered_task.count(material) != 1:
            raise AutomaticRuntimeError("runtime material delivery is duplicated")
        receipt = RuntimeDeliveryReceipt(
            receipt_id=receipt_id,
            task_ref=task_ref,
            target_family=TargetKind.CODEX.value,
            original_task_digest=sha256_text(normalized_task),
            external_release_digest=release.governed_release.content_digest,
            composed_release_digest=release.content_digest,
            projection_digest=projection.content_digest,
            projection_manifest_digest=manifest.content_digest,
            material_digest=rendered.content_digest,
            material_utf8_bytes=rendered.utf8_bytes,
            delivered_task_digest=sha256_text(delivered_task),
            material_occurrences=0 if not material else 1,
            delivered_at=delivered_at,
        )
        return PreparedRuntimeTask(
            original_task=normalized_task,
            delivered_task=delivered_task,
            rendered_material=rendered,
            receipt=receipt,
        )

    def _governance_event(
        self,
        *,
        event_id: str,
        event_type: GovernanceEventType,
        target_ref: str,
        target_digest: str,
        decision: str,
        reason: str,
        occurred_at: datetime,
    ) -> GovernanceEvent:
        return sign_governance_event(
            {
                "event_id": event_id,
                "subject_id": self._policy.subject_id,
                "event_type": event_type.value,
                "target_ref": target_ref,
                "target_digest": target_digest,
                "decision": decision,
                "reason": reason,
                "policy_version": self._policy.policy_version,
                "occurred_at": occurred_at.isoformat(),
            },
            self._signer,
        )

    def _notice(
        self,
        detection: DetectedFeedback,
        created_at: datetime,
        *,
        transition: RuntimeLearningTransition | None = None,
    ) -> RuntimeNotice:
        mapping = {
            AutomationDisposition.IGNORED_UNTRUSTED: (
                RuntimeNoticeKind.IGNORED,
                "Ignored non-user content; it was not learned.",
            ),
            AutomationDisposition.NO_EXPLICIT_SIGNAL: (
                RuntimeNoticeKind.IGNORED,
                "No durable learning detected.",
            ),
            AutomationDisposition.REVIEW_REQUIRED: (
                RuntimeNoticeKind.NEEDS_REVIEW,
                "Captured a possible adaptation for review; it is not active.",
            ),
            AutomationDisposition.BLOCKED: (
                RuntimeNoticeKind.BLOCKED,
                "Blocked unsafe adaptation content.",
            ),
            AutomationDisposition.DUPLICATE: (
                RuntimeNoticeKind.UNCHANGED,
                "An identical scoped adaptation is already active.",
            ),
            AutomationDisposition.PROMOTED: (
                RuntimeNoticeKind.UPDATED
                if detection.signal_kind is FeedbackSignalKind.CORRECTION
                else RuntimeNoticeKind.LEARNED,
                "Updated the scoped adaptation."
                if detection.signal_kind is FeedbackSignalKind.CORRECTION
                else "Learned one scoped adaptation.",
            ),
            AutomationDisposition.REVOKED: (
                RuntimeNoticeKind.REMOVED,
                "Removed one scoped adaptation.",
            ),
        }
        kind, summary = mapping[detection.disposition]
        introduced_id = (
            None
            if transition is None or transition.instruction is None
            else transition.instruction.artifact_ref.record_id
        )
        return RuntimeNotice(
            notice_id=f"notice-{detection.candidate_id}",
            kind=kind,
            summary=summary,
            transition_id=None if transition is None else transition.transition_id,
            undo_artifact_id=introduced_id,
            created_at=created_at,
        )

    def _unchanged_cycle(
        self,
        *,
        observation: InteractionObservation,
        state: AutomaticRuntimeState,
        detection: DetectedFeedback,
        notice: RuntimeNotice,
        processed_at: datetime,
    ) -> RuntimeCycleReceipt:
        return RuntimeCycleReceipt(
            cycle_id=f"cycle-{observation.observation_id}",
            subject_id=observation.subject_id,
            observation_id=observation.observation_id,
            observation_digest=observation.content_digest,
            prior_state_digest=state.content_digest,
            resulting_state_digest=state.content_digest,
            disposition=detection.disposition,
            detected_feedback_digest=detection.content_digest,
            automatic_actions=1,
            notice=notice,
            created_at=processed_at,
        )

    def _approved_privacy(
        self,
        consent_id: str,
        actor: ActorRef,
        reviewed_at: datetime,
    ) -> PrivacyContext:
        return PrivacyContext(
            sensitivity=SensitivityClass.PRIVATE,
            consent_basis=consent_id,
            permitted_uses=self._policy.permitted_uses,
            review_state=PrivacyReviewState.APPROVED,
            reviewed_by=actor,
            reviewed_at=reviewed_at,
            notes="Approved within the exact signed standing-automation policy.",
        )

    @staticmethod
    def _claim_types(detection: DetectedFeedback) -> tuple[ClaimType, ...]:
        if detection.signal_kind in {
            FeedbackSignalKind.CORRECTION,
            FeedbackSignalKind.REVOCATION,
        }:
            return (ClaimType.USER_CORRECTION,)
        if detection.signal_kind is FeedbackSignalKind.POSITIVE_EXAMPLE:
            return (ClaimType.USER_ACCEPTANCE,)
        return (ClaimType.USER_PREFERENCE,)

    @property
    def _runtime_actor(self) -> ActorRef:
        return ActorRef(
            actor_id="automatic-runtime",
            kind=ActorKind.SYSTEM,
            display_name="Automatic Adaptation Runtime",
            version="1.0.0",
        )

    @property
    def _user_actor(self) -> ActorRef:
        return ActorRef(
            actor_id=self._policy.subject_id,
            kind=ActorKind.USER,
            display_name="Local adaptation owner",
        )

    @staticmethod
    def _evidence_ref(evidence: Evidence) -> EvidenceRef:
        return EvidenceRef(
            record_id=evidence.record_id,
            record_version=evidence.record_version,
            content_digest=canonical_digest(evidence),
        )

    @staticmethod
    def _active_artifact(
        state: AutomaticRuntimeState,
        artifact_id: str | None,
    ) -> ArtifactRenderProjection | None:
        if state.release is None or artifact_id is None:
            return None
        return next(
            (
                item
                for item in state.release.governed_release.active_artifacts
                if item.artifact_ref.record_id == artifact_id
            ),
            None,
        )

    @staticmethod
    def _scope_equal_or_narrower(child: Scope, parent: Scope) -> bool:
        from adaptation_compiler_lab.domain.values import scope_is_within

        return child == parent or scope_is_within(child, parent)
