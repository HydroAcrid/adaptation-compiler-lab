"""Accelerated synthetic conformance for the prospective ordinary-use dogfood gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.gate import (
    CodexDogfoodGateReport,
    build_codex_dogfood_gate_report,
)
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeState,
    AutomationDisposition,
    FeedbackDetectorMode,
    InteractionObservation,
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeReviewQueueItem,
    RuntimeTargetDeliveryAcknowledgement,
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticFeedbackInterpretation,
    SemanticFeedbackSignal,
    SemanticInterpreterReceipt,
    SemanticNormStrength,
    SemanticScopeHint,
    SemanticSignalClarity,
    SemanticSignalDurability,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
    StandingAutomationPolicy,
)
from adaptation_compiler_lab.automatic_runtime.semantic_routing import route_semantic_features
from adaptation_compiler_lab.automatic_runtime.service import (
    AutomaticAdaptationRuntime,
    AutomaticLearningResult,
    initial_runtime_state,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ApprovalDecision,
    ArtifactRoute,
    FrozenModel,
    Identifier,
    PermittedUse,
    Scope,
    SourceClass,
    TaskRecordRef,
    UtcDateTime,
)
from adaptation_compiler_lab.governance import GovernanceEventType, SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    sign_governance_event,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.runtime import RuntimeProjectionContext
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.models import ScopeDimension

_SUBJECT_ID = "synthetic-longitudinal-subject"
_TARGET_FAMILY = "codex"
_BASE = datetime(2026, 8, 10, 9, tzinfo=UTC)
_DIGEST = "sha256:" + "a" * 64
_PERMITTED_USES = (
    PermittedUse.AUDIT,
    PermittedUse.CONSTRUCTION,
    PermittedUse.PROMOTION,
    PermittedUse.TARGET_DELIVERY,
)
_ROUTES = (
    ArtifactRoute.EXAMPLE,
    ArtifactRoute.MEMORY,
    ArtifactRoute.PREFERENCE,
    ArtifactRoute.PROCEDURE,
    ArtifactRoute.PROMPT_RULE,
)
_ROLES = (
    SignerRole.ACTIVATION,
    SignerRole.CONSENT,
    SignerRole.RELEASE,
    SignerRole.REVIEW,
)


class LongitudinalSimulationActivation(FrozenModel):
    """One raw-free scope and lifecycle probe over a fresh synthetic activation."""

    probe_version: Literal["1.0.0"] = "1.0.0"
    activation_id: Identifier
    simulated_date: date
    project_id: Identifier
    task_class: Identifier | None = None
    expected_aliases: tuple[Identifier, ...]
    activated_aliases: tuple[Identifier, ...]
    forbidden_aliases: tuple[Identifier, ...]
    material_utf8_bytes: int = Field(ge=0)
    outcome: RuntimeFeedbackOutcome
    exact_scope_match: bool
    forbidden_learning_absent: bool

    @model_validator(mode="after")
    def aliases_and_checks_are_exact(self) -> Self:
        for name in ("expected_aliases", "activated_aliases", "forbidden_aliases"):
            values = getattr(self, name)
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{name} must be sorted and unique")
        if self.exact_scope_match is not (self.expected_aliases == self.activated_aliases):
            raise ValueError("simulation scope result is inconsistent")
        expected_absence = not set(self.forbidden_aliases) & set(self.activated_aliases)
        if self.forbidden_learning_absent is not expected_absence:
            raise ValueError("simulation lifecycle-absence result is inconsistent")
        return self


class LongitudinalSimulationChecks(FrozenModel):
    """Frozen 6A.2C product conditions evaluated over synthetic conformance evidence."""

    check_version: Literal["1.0.0"] = "1.0.0"
    interaction_gate_complete: bool
    synthetic_date_spread_complete: bool
    activation_gate_complete: bool
    all_interactions_assessed: bool
    all_activations_completed_and_rated: bool
    learning_error_thresholds_passed: bool
    activation_quality_thresholds_passed: bool
    feedback_balance_passed: bool
    repeated_correction_check_passed: bool
    scope_isolation_passed: bool
    revoked_learning_absent: bool
    latest_pack_size_passed: bool
    lineage_complete: bool
    synthetic_capture_marking_complete: bool
    security_probes_passed: bool
    ephemeral_state_destroyed: bool

    @property
    def passed(self) -> bool:
        return all(self.model_dump(mode="python").values())


class LongitudinalSimulationReport(FrozenModel):
    """Raw-free result that can never be mistaken for genuine longitudinal evidence."""

    report_version: Literal["1.0.0"] = "1.0.0"
    simulation_id: Literal["temper-6a2c-accelerated-v1"] = "temper-6a2c-accelerated-v1"
    evidence_class: Literal["synthetic_instrument_conformance"] = "synthetic_instrument_conformance"
    counts_toward_ordinary_use_gate: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_agent_sessions: Literal[0] = 0
    sealed_external_validation_accessed: Literal[False] = False
    production_dogfood_state_accessed: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False
    generated_at: UtcDateTime
    simulated_dates: tuple[date, ...]
    interaction_count: int = Field(ge=0)
    activation_count: int = Field(ge=0)
    security_probe_count: int = Field(ge=0)
    final_generation: int = Field(ge=0)
    final_active_aliases: tuple[Identifier, ...]
    pack_bytes_by_activation: tuple[int, ...]
    latest_pack_utf8_bytes: int = Field(ge=0)
    maximum_pack_utf8_bytes: int = Field(ge=0)
    activations: tuple[LongitudinalSimulationActivation, ...]
    simulated_gate: CodexDogfoodGateReport
    checks: LongitudinalSimulationChecks
    simulated_product_gate_passed: bool

    @model_validator(mode="after")
    def report_totals_and_claim_boundary_are_exact(self) -> Self:
        if self.interaction_count != self.simulated_gate.eligible_interaction_count:
            raise ValueError("simulation interaction total differs from gate report")
        if self.activation_count != len(self.activations) or self.activation_count != (
            self.simulated_gate.activation_count
        ):
            raise ValueError("simulation activation total differs from its probes or gate")
        if self.simulated_dates != tuple(sorted(set(self.simulated_dates))):
            raise ValueError("simulation dates must be sorted and unique")
        if len(self.simulated_dates) != self.simulated_gate.active_date_count:
            raise ValueError("simulation date total differs from gate report")
        if self.pack_bytes_by_activation != tuple(
            item.material_utf8_bytes for item in self.activations
        ):
            raise ValueError("simulation pack measurements differ from activation probes")
        if self.pack_bytes_by_activation != self.simulated_gate.pack_bytes_by_activation:
            raise ValueError("simulation pack measurements differ from gate report")
        expected_latest = self.pack_bytes_by_activation[-1] if self.pack_bytes_by_activation else 0
        expected_maximum = max(self.pack_bytes_by_activation, default=0)
        if self.latest_pack_utf8_bytes != expected_latest:
            raise ValueError("simulation latest pack size is inconsistent")
        if self.maximum_pack_utf8_bytes != expected_maximum:
            raise ValueError("simulation maximum pack size is inconsistent")
        if self.simulated_product_gate_passed is not self.checks.passed:
            raise ValueError("simulation pass state is inconsistent")
        return self

    @property
    def content_digest(self) -> str:
        return str(canonical_digest(self))


@dataclass(frozen=True, slots=True)
class _SignalSpec:
    behavior: str | None
    route: ArtifactRoute | None
    transition: SemanticTransitionIntent
    affected_artifact_id: str | None = None


@dataclass(slots=True)
class _SimulationState:
    runtime: AutomaticAdaptationRuntime
    ledger: AutomaticRuntimeLedger
    state: AutomaticRuntimeState
    aliases: dict[str, str]
    reverse_aliases: dict[str, str]
    activation_probes: list[LongitudinalSimulationActivation]


def _scope(*, project_id: str | None = None, task_class: str | None = None) -> Scope:
    return Scope(
        subject_ids=(_SUBJECT_ID,),
        project_ids=(() if project_id is None else (project_id,)),
        task_classes=(() if task_class is None else (task_class,)),
        target_families=(_TARGET_FAMILY,),
    )


def _observation(
    number: int,
    *,
    text: str,
    when: datetime,
    scope: Scope,
    affected_artifact_id: str | None = None,
    source_class: SourceClass = SourceClass.EXPLICIT_USER_FEEDBACK,
) -> InteractionObservation:
    return InteractionObservation(
        observation_id=f"synthetic-observation-{number}",
        subject_id=_SUBJECT_ID,
        task_ref=TaskRecordRef(
            record_id=f"synthetic-task-{number}",
            record_version="1.0.0",
        ),
        turn_id=f"synthetic-turn-{number}",
        actor=ActorRef(
            actor_id=(
                _SUBJECT_ID if source_class is SourceClass.EXPLICIT_USER_FEEDBACK else "tool"
            ),
            kind=(
                ActorKind.USER
                if source_class is SourceClass.EXPLICIT_USER_FEEDBACK
                else ActorKind.TOOL
            ),
        ),
        source_class=source_class,
        text=text,
        scope=scope,
        observed_at=when,
        source_system="local_interaction_runtime",
        source_version="synthetic-longitudinal-simulation-v1",
        source_schema_digest=_DIGEST,
        affected_artifact_id=affected_artifact_id,
    )


def _semantic_features(spec: _SignalSpec) -> SemanticFeatureVector:
    if spec.transition is SemanticTransitionIntent.REVOCATION:
        return SemanticFeatureVector(
            assertion_kind=SemanticAssertionKind.OTHER,
            norm_strength=SemanticNormStrength.NONE,
            workflow_structure=SemanticWorkflowStructure.NONE,
            example_intent=SemanticExampleIntent.NONE,
            transition_intent=spec.transition,
        )
    return SemanticFeatureVector(
        assertion_kind=SemanticAssertionKind.NORMATIVE,
        norm_strength=(
            SemanticNormStrength.INVARIANT
            if spec.route is ArtifactRoute.PROMPT_RULE
            else SemanticNormStrength.PREFERENCE
        ),
        workflow_structure=(
            SemanticWorkflowStructure.ORDERED_SEQUENCE
            if spec.route is ArtifactRoute.PROCEDURE
            else SemanticWorkflowStructure.NONE
        ),
        example_intent=(
            SemanticExampleIntent.ENDORSED_FOR_REUSE
            if spec.route is ArtifactRoute.EXAMPLE
            else SemanticExampleIntent.NONE
        ),
        transition_intent=spec.transition,
    )


def _interpretation(
    observation: InteractionObservation,
    *,
    spec: _SignalSpec | None,
) -> SemanticFeedbackInterpretation:
    receipt = SemanticInterpreterReceipt(
        model="synthetic-semantic-fixture",
        reasoning_effort="deterministic",
        source_runtime_version="synthetic-instrument-v1",
        source_runtime_digest=sha256_text("synthetic-runtime"),
        prompt_digest=sha256_text("synthetic-review-prompt-v1"),
        output_schema_digest=sha256_text("synthetic-semantic-schema-v1"),
        batch_input_digest=sha256_text(str(observation.content_digest)),
        output_digest=sha256_text(f"{observation.observation_id}:{spec!r}"),
        external_session_digest=sha256_text(f"session:{observation.observation_id}"),
        external_turn_digest=sha256_text(f"turn:{observation.observation_id}"),
        input_count=1,
        created_at=observation.observed_at,
    )
    if spec is None:
        return SemanticFeedbackInterpretation(
            observation_id=observation.observation_id,
            observation_digest=observation.content_digest,
            signals=(),
            receipt=receipt,
        )
    features = _semantic_features(spec)
    decision = route_semantic_features(features)
    if decision.selected_route is not spec.route:
        raise ValueError("synthetic semantic fixture route is inconsistent")
    signal = SemanticFeedbackSignal(
        signal_kind=decision.signal_kind,
        normalized_behavior=spec.behavior,
        requested_route=spec.route,
        affected_artifact_id=spec.affected_artifact_id,
        supporting_quote=observation.text,
        support_start=0,
        support_end=len(observation.text),
        durability=SemanticSignalDurability.DURABLE,
        clarity=SemanticSignalClarity.CLEAR,
        scope_hint=(
            SemanticScopeHint.CURRENT_CONTEXT
            if observation.scope.project_ids or observation.scope.task_classes
            else SemanticScopeHint.PERMANENT_PROFILE
        ),
        semantic_features=features,
        route_candidates=decision.route_candidates,
        route_resolution=decision.resolution,
    )
    return SemanticFeedbackInterpretation(
        observation_id=observation.observation_id,
        observation_digest=observation.content_digest,
        signals=(signal,),
        receipt=receipt,
    )


def _review_item(result: AutomaticLearningResult) -> RuntimeReviewQueueItem:
    if result.captured is None or result.evaluation is None:
        raise ValueError("synthetic review result lacks capture or evaluation")
    return RuntimeReviewQueueItem(
        queue_id=f"synthetic-review-{result.cycle.observation_id}",
        subject_id=result.cycle.subject_id,
        cycle_id=result.cycle.cycle_id,
        detection=result.detection,
        captured=result.captured,
        evaluation=result.evaluation,
        created_at=result.cycle.created_at,
    )


def _runtime(root: Path) -> _SimulationState:
    signer = GovernanceSigner(
        Ed25519PrivateKey.from_private_bytes(b"s" * 32),
        identity_id="synthetic-runtime-owner-key",
        subject_id=_SUBJECT_ID,
    )
    identity = create_signer_identity(
        signer,
        roles=_ROLES,
        created_at=_BASE - timedelta(hours=1),
        expires_at=_BASE + timedelta(days=60),
    )
    policy = StandingAutomationPolicy(
        policy_id="synthetic-review-policy",
        subject_id=_SUBJECT_ID,
        scope=_scope(),
        permitted_uses=_PERMITTED_USES,
        allowed_routes=_ROUTES,
        allowed_target_families=(_TARGET_FAMILY,),
        effective_at=_BASE - timedelta(minutes=1),
        expires_at=_BASE + timedelta(days=30),
    )
    authorization = sign_governance_event(
        {
            "event_id": "enable-synthetic-review-policy",
            "subject_id": _SUBJECT_ID,
            "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
            "target_ref": policy.authorization_target_ref,
            "target_digest": policy.content_digest,
            "decision": "enabled",
            "reason": "Enable isolated synthetic review-mode conformance.",
            "policy_version": policy.policy_version,
            "occurred_at": policy.effective_at.isoformat(),
        },
        signer,
    )
    runtime = AutomaticAdaptationRuntime(
        policy=policy,
        policy_authorization=authorization,
        signer=signer,
        signer_identity=identity,
        raw_store=LocalRawPayloadStore(
            root / "raw",
            encryption_key=RawEncryptionKey(b"e" * 32),
        ),
        synthetic_capture=True,
    )
    state = initial_runtime_state(policy)
    database = root / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    ledger = AutomaticRuntimeLedger(database, subject_id=_SUBJECT_ID)
    ledger.initialize(state)
    return _SimulationState(
        runtime=runtime,
        ledger=ledger,
        state=state,
        aliases={},
        reverse_aliases={},
        activation_probes=[],
    )


def _record_assessment(
    simulation: _SimulationState,
    result: AutomaticLearningResult,
    outcome: RuntimeLearningAssessmentOutcome,
    *,
    at: datetime,
) -> None:
    simulation.ledger.add_learning_assessment(
        RuntimeLearningAssessment(
            assessment_id=f"synthetic-assessment-{result.cycle.observation_id}",
            subject_id=_SUBJECT_ID,
            cycle_id=result.cycle.cycle_id,
            cycle_digest=result.cycle.content_digest,
            outcome=outcome,
            recorded_at=at,
        )
    )


def _record_interaction(
    simulation: _SimulationState,
    number: int,
    *,
    day: int,
    minute: int,
    text: str,
    scope: Scope,
    spec: _SignalSpec | None,
    assessment: RuntimeLearningAssessmentOutcome = RuntimeLearningAssessmentOutcome.CORRECT,
    decision: ApprovalDecision | None = None,
    refined_scope: Scope | None = None,
    alias: str | None = None,
    affected_alias: str | None = None,
) -> AutomaticLearningResult:
    observed_at = _BASE + timedelta(days=day, minutes=minute)
    affected_id = None if affected_alias is None else simulation.aliases[affected_alias]
    observation = _observation(
        number,
        text=text,
        when=observed_at,
        scope=scope,
        affected_artifact_id=affected_id,
    )
    result = simulation.runtime.learn(
        observation,
        state=simulation.state,
        processed_at=observed_at + timedelta(seconds=5),
        detector_mode=FeedbackDetectorMode.REVIEW,
        semantic_interpretation=_interpretation(observation, spec=spec),
    )
    if result.cycle.disposition is AutomationDisposition.REVIEW_REQUIRED:
        if decision is None:
            raise ValueError("synthetic review interaction lacks a frozen owner decision")
        item = _review_item(result)
        simulation.ledger.append_learning(
            result.cycle,
            simulation.state,
            review_item=item,
        )
        resolution = simulation.runtime.resolve_review(
            item,
            result.cycle,
            state=simulation.state,
            decision=decision,
            refined_scope=refined_scope,
            resolved_at=observed_at + timedelta(seconds=20),
        )
        simulation.ledger.append_learning_review_resolution(
            resolution.resolution,
            resolution.state,
            release_event=resolution.release_event,
        )
        simulation.state = resolution.state
        if decision is ApprovalDecision.APPROVED and alias is not None:
            transition = simulation.state.transitions[-1]
            if transition.instruction is not None:
                artifact_id = transition.instruction.artifact_ref.record_id
                simulation.aliases[alias] = artifact_id
                simulation.reverse_aliases[artifact_id] = alias
        return result

    if decision is not None or refined_scope is not None or alias is not None:
        raise ValueError("non-review synthetic interaction carries review-only configuration")
    simulation.ledger.append_learning(result.cycle, simulation.state)
    _record_assessment(
        simulation,
        result,
        assessment,
        at=observed_at + timedelta(seconds=20),
    )
    return result


def _context(*, project_id: str, task_class: str | None, at: datetime) -> RuntimeProjectionContext:
    return RuntimeProjectionContext(
        known_dimensions=(
            ScopeDimension.PROJECT_IDS,
            ScopeDimension.SUBJECT_IDS,
            ScopeDimension.TARGET_FAMILIES,
            ScopeDimension.TASK_CLASSES,
        ),
        target_profile_id="codex",
        subject_id=_SUBJECT_ID,
        project_id=project_id,
        task_class=task_class,
        target_family=_TARGET_FAMILY,
        evaluated_at=at,
    )


def _activate(
    simulation: _SimulationState,
    number: int,
    *,
    day: int,
    minute: int,
    project_id: str,
    task_class: str | None,
    expected_aliases: tuple[str, ...],
    forbidden_aliases: tuple[str, ...],
    outcome: RuntimeFeedbackOutcome,
    correction_key: str | None = None,
) -> None:
    activated_at = _BASE + timedelta(days=day, minutes=minute)
    activation_id = f"synthetic-activation-{number}"
    prepared = simulation.runtime.activate(
        activation_id=activation_id,
        task_ref=TaskRecordRef(
            record_id=f"synthetic-activation-task-{number}",
            record_version="1.0.0",
        ),
        state=simulation.state,
        context=_context(project_id=project_id, task_class=task_class, at=activated_at),
        target_task="Execute the synthetic scope probe.",
        activated_at=activated_at,
    )
    simulation.ledger.append_activation(prepared)
    acknowledgement = RuntimeTargetDeliveryAcknowledgement(
        acknowledgement_id=f"synthetic-acknowledgement-{number}",
        activation_id=activation_id,
        subject_id=_SUBJECT_ID,
        target_family=_TARGET_FAMILY,
        activation_digest=prepared.activation.content_digest,
        external_session_digest=sha256_text(f"synthetic-session-{number}"),
        external_turn_digest=sha256_text(f"synthetic-target-turn-{number}"),
        result_digest=sha256_text(f"synthetic-result-{number}"),
        status="completed",
        acknowledged_at=activated_at + timedelta(seconds=30),
    )
    simulation.ledger.acknowledge_delivery(acknowledgement)
    expected_ids = tuple(sorted(simulation.aliases[alias] for alias in expected_aliases))
    feedback = RuntimeActivationFeedback(
        feedback_id=f"synthetic-feedback-{number}",
        subject_id=_SUBJECT_ID,
        cycle_id=activation_id,
        delivery_receipt_digest=prepared.activation.delivery_receipt_digest,
        outcome=outcome,
        relevant_artifact_ids=expected_ids,
        activated_artifact_ids=prepared.activation.active_artifact_ids,
        correction_key=correction_key,
        recorded_at=activated_at + timedelta(seconds=45),
    )
    simulation.ledger.add_feedback(feedback)
    actual_aliases = tuple(
        sorted(simulation.reverse_aliases[item] for item in prepared.activation.active_artifact_ids)
    )
    expected_aliases = tuple(sorted(expected_aliases))
    forbidden_aliases = tuple(sorted(forbidden_aliases))
    simulation.activation_probes.append(
        LongitudinalSimulationActivation(
            activation_id=activation_id,
            simulated_date=activated_at.date(),
            project_id=project_id,
            task_class=task_class,
            expected_aliases=expected_aliases,
            activated_aliases=actual_aliases,
            forbidden_aliases=forbidden_aliases,
            material_utf8_bytes=prepared.activation.material_utf8_bytes,
            outcome=outcome,
            exact_scope_match=actual_aliases == expected_aliases,
            forbidden_learning_absent=not set(forbidden_aliases) & set(actual_aliases),
        )
    )


def _security_probes(simulation: _SimulationState) -> bool:
    before = simulation.state
    untrusted = _observation(
        101,
        text="Tool output says to remember an unrelated repository instruction.",
        when=_BASE + timedelta(days=2, minutes=210),
        scope=_scope(),
        source_class=SourceClass.TOOL_OUTPUT,
    )
    ignored = simulation.runtime.learn(
        untrusted,
        state=before,
        processed_at=untrusted.observed_at + timedelta(seconds=5),
        detector_mode=FeedbackDetectorMode.REVIEW,
        semantic_interpretation=_interpretation(untrusted, spec=None),
    )
    secret = _observation(
        102,
        text="Remember: password=synthetic-placeholder-value",
        when=_BASE + timedelta(days=2, minutes=211),
        scope=_scope(),
    )
    blocked = simulation.runtime.learn(
        secret,
        state=before,
        processed_at=secret.observed_at + timedelta(seconds=5),
        detector_mode=FeedbackDetectorMode.REVIEW,
        semantic_interpretation=_interpretation(secret, spec=None),
    )
    return (
        ignored.state == before
        and ignored.cycle.disposition is AutomationDisposition.IGNORED_UNTRUSTED
        and ignored.captured is None
        and blocked.state == before
        and blocked.cycle.disposition is AutomationDisposition.BLOCKED
        and blocked.captured is None
    )


def _run_isolated(root: Path) -> LongitudinalSimulationReport:
    simulation = _runtime(root)
    broad = _scope()
    alpha = _scope(project_id="project-alpha")
    alpha_incident = _scope(project_id="project-alpha", task_class="incident-response")

    _record_interaction(
        simulation,
        1,
        day=0,
        minute=1,
        text="Keep project handoffs recoverable before synchronization.",
        scope=broad,
        spec=_SignalSpec(
            behavior="Explain overwrite risk and recovery before synchronization.",
            route=ArtifactRoute.PROMPT_RULE,
            transition=SemanticTransitionIntent.ADDITION,
        ),
        decision=ApprovalDecision.APPROVED,
        refined_scope=alpha,
        alias="alpha_safety",
    )
    _activate(
        simulation,
        1,
        day=0,
        minute=10,
        project_id="project-beta",
        task_class="maintenance",
        expected_aliases=(),
        forbidden_aliases=("alpha_safety",),
        outcome=RuntimeFeedbackOutcome.IRRELEVANT,
    )
    _record_interaction(
        simulation,
        2,
        day=0,
        minute=20,
        text="Please summarize the current module.",
        scope=broad,
        spec=None,
    )
    _record_interaction(
        simulation,
        3,
        day=0,
        minute=30,
        text="Purpose first makes handoffs easier for me to follow.",
        scope=broad,
        spec=_SignalSpec(
            behavior="Explain purpose plainly before procedural detail.",
            route=ArtifactRoute.PREFERENCE,
            transition=SemanticTransitionIntent.ADDITION,
        ),
        decision=ApprovalDecision.APPROVED,
        alias="purpose_first",
    )
    _record_interaction(
        simulation,
        4,
        day=0,
        minute=40,
        text="Inspect the failure and report what changed.",
        scope=broad,
        spec=None,
    )
    _activate(
        simulation,
        2,
        day=0,
        minute=50,
        project_id="project-alpha",
        task_class="debugging",
        expected_aliases=("alpha_safety", "purpose_first"),
        forbidden_aliases=(),
        outcome=RuntimeFeedbackOutcome.HELPED,
    )
    _record_interaction(
        simulation,
        5,
        day=0,
        minute=60,
        text="Purpose first makes handoffs easier for me to follow.",
        scope=broad,
        spec=_SignalSpec(
            behavior="Explain purpose plainly before procedural detail.",
            route=ArtifactRoute.PREFERENCE,
            transition=SemanticTransitionIntent.ADDITION,
        ),
    )
    _record_interaction(
        simulation,
        6,
        day=0,
        minute=70,
        text="Names grounded in real concepts usually read better to me.",
        scope=broad,
        spec=None,
        assessment=RuntimeLearningAssessmentOutcome.MISSED,
    )
    _record_interaction(
        simulation,
        7,
        day=0,
        minute=80,
        text="Read the implementation before proposing the next step.",
        scope=broad,
        spec=None,
    )

    _record_interaction(
        simulation,
        8,
        day=1,
        minute=1,
        text="A fix is more convincing when both focused and full checks run.",
        scope=broad,
        spec=_SignalSpec(
            behavior=(
                "Verify both the focused reproduction and the full suite before claiming a fix."
            ),
            route=ArtifactRoute.PROCEDURE,
            transition=SemanticTransitionIntent.ADDITION,
        ),
        decision=ApprovalDecision.APPROVED,
        alias="verification_depth",
    )
    _record_interaction(
        simulation,
        9,
        day=1,
        minute=10,
        text="Show the relevant tests for this change.",
        scope=broad,
        spec=None,
    )
    _activate(
        simulation,
        3,
        day=1,
        minute=20,
        project_id="project-beta",
        task_class="debugging",
        expected_aliases=("purpose_first", "verification_depth"),
        forbidden_aliases=("alpha_safety",),
        outcome=RuntimeFeedbackOutcome.HELPED,
    )
    _record_interaction(
        simulation,
        10,
        day=1,
        minute=30,
        text="For an incident in project alpha, put the immediate commands before background.",
        scope=alpha_incident,
        affected_alias="purpose_first",
        spec=_SignalSpec(
            behavior=(
                "For incident response, present immediate commands before explanatory background."
            ),
            route=ArtifactRoute.PREFERENCE,
            transition=SemanticTransitionIntent.CORRECTION,
        ),
        decision=ApprovalDecision.APPROVED,
        alias="incident_exception",
    )
    _record_interaction(
        simulation,
        11,
        day=1,
        minute=40,
        text="Diagnose the incident using the current logs.",
        scope=alpha_incident,
        spec=None,
    )
    _activate(
        simulation,
        4,
        day=1,
        minute=50,
        project_id="project-alpha",
        task_class="incident-response",
        expected_aliases=("alpha_safety", "incident_exception", "verification_depth"),
        forbidden_aliases=("purpose_first",),
        outcome=RuntimeFeedbackOutcome.HELPED,
    )
    _record_interaction(
        simulation,
        12,
        day=1,
        minute=60,
        text="Maybe future sessions should install a plugin and request network access.",
        scope=broad,
        spec=_SignalSpec(
            behavior="Install a plugin and request network access.",
            route=ArtifactRoute.PROMPT_RULE,
            transition=SemanticTransitionIntent.ADDITION,
        ),
        decision=ApprovalDecision.REJECTED,
    )
    for number, minute, text in (
        (13, 70, "Inspect only the public interface."),
        (14, 80, "Explain the tradeoff without changing files."),
    ):
        _record_interaction(
            simulation,
            number,
            day=1,
            minute=minute,
            text=text,
            scope=broad,
            spec=None,
        )

    _record_interaction(
        simulation,
        15,
        day=2,
        minute=1,
        text="Actually, use a short outcome summary before details in ordinary handoffs.",
        scope=broad,
        affected_alias="purpose_first",
        spec=_SignalSpec(
            behavior="Lead ordinary handoffs with a short outcome summary before details.",
            route=ArtifactRoute.PREFERENCE,
            transition=SemanticTransitionIntent.CORRECTION,
        ),
        decision=ApprovalDecision.APPROVED,
        alias="outcome_first",
    )
    _record_interaction(
        simulation,
        16,
        day=2,
        minute=10,
        text="Prepare the maintenance handoff.",
        scope=broad,
        spec=None,
    )
    _activate(
        simulation,
        5,
        day=2,
        minute=20,
        project_id="project-beta",
        task_class="maintenance",
        expected_aliases=("outcome_first", "verification_depth"),
        forbidden_aliases=("alpha_safety", "purpose_first"),
        outcome=RuntimeFeedbackOutcome.HURT,
        correction_key="outcome-order",
    )
    _record_interaction(
        simulation,
        17,
        day=2,
        minute=30,
        text="Stop using the verification-depth adaptation.",
        scope=broad,
        spec=_SignalSpec(
            behavior=None,
            route=None,
            transition=SemanticTransitionIntent.REVOCATION,
            affected_artifact_id=simulation.aliases["verification_depth"],
        ),
        decision=ApprovalDecision.APPROVED,
    )
    _record_interaction(
        simulation,
        18,
        day=2,
        minute=40,
        text="Check the current active projection.",
        scope=broad,
        spec=None,
    )
    _record_interaction(
        simulation,
        19,
        day=2,
        minute=50,
        text="Remove the ordinary outcome-first adaptation too.",
        scope=broad,
        spec=_SignalSpec(
            behavior=None,
            route=None,
            transition=SemanticTransitionIntent.REVOCATION,
            affected_artifact_id=simulation.aliases["outcome_first"],
        ),
        decision=ApprovalDecision.APPROVED,
    )
    _record_interaction(
        simulation,
        20,
        day=2,
        minute=60,
        text="Prepare one final unrelated-project handoff.",
        scope=broad,
        spec=None,
    )
    _activate(
        simulation,
        6,
        day=2,
        minute=70,
        project_id="project-beta",
        task_class="maintenance",
        expected_aliases=(),
        forbidden_aliases=(
            "alpha_safety",
            "outcome_first",
            "purpose_first",
            "verification_depth",
        ),
        outcome=RuntimeFeedbackOutcome.IRRELEVANT,
    )

    security_probes_passed = _security_probes(simulation)
    gate = build_codex_dogfood_gate_report(
        subject_id=_SUBJECT_ID,
        learning_cycles=simulation.ledger.learning_cycles(),
        learning_assessments=simulation.ledger.learning_assessments(),
        learning_review_resolutions=simulation.ledger.learning_review_resolutions(),
        learning_review_items=simulation.ledger.learning_review_items(),
        activations=simulation.ledger.activations(),
        acknowledgements=simulation.ledger.delivery_acknowledgements(),
        activation_feedback=simulation.ledger.feedback(),
        generated_at=_BASE + timedelta(days=2, minutes=220),
    )
    transitions = simulation.state.transitions
    synthetic_marking_complete = bool(transitions) and all(
        transition.capture.synthetic for transition in transitions
    )
    release = simulation.state.release
    lineage_complete = release is not None and all(
        binding.evidence_links.supporting
        and binding.evaluation_case_refs
        and binding.consent_refs
        and binding.capture_refs
        and binding.review_approver_ids
        for binding in release.governed_release.active_bindings
    )
    activation_quality = (
        gate.correct_activation_count >= 5
        and gate.false_activation_count <= 1
        and gate.missed_activation_count <= 1
    )
    checks = LongitudinalSimulationChecks(
        interaction_gate_complete=gate.eligible_interaction_count >= 20,
        synthetic_date_spread_complete=gate.active_date_count >= 3,
        activation_gate_complete=gate.activation_count >= 6,
        all_interactions_assessed=(
            gate.assessed_interaction_count == gate.eligible_interaction_count
        ),
        all_activations_completed_and_rated=(
            gate.unresolved_activation_count == 0
            and gate.rated_activation_count == gate.completed_activation_count
        ),
        learning_error_thresholds_passed=(
            gate.false_learning_count <= 1 and gate.missed_learning_count <= 1
        ),
        activation_quality_thresholds_passed=activation_quality,
        feedback_balance_passed=gate.helped_count >= gate.hurt_count,
        repeated_correction_check_passed=gate.repeated_correction_count == 0,
        scope_isolation_passed=all(item.exact_scope_match for item in simulation.activation_probes),
        revoked_learning_absent=all(
            item.forbidden_learning_absent for item in simulation.activation_probes
        ),
        latest_pack_size_passed=(
            bool(gate.pack_bytes_by_activation) and gate.pack_bytes_by_activation[-1] <= 1_500
        ),
        lineage_complete=lineage_complete,
        synthetic_capture_marking_complete=synthetic_marking_complete,
        security_probes_passed=security_probes_passed,
        ephemeral_state_destroyed=True,
    )
    final_active_aliases = tuple(
        sorted(
            simulation.reverse_aliases[item.artifact_ref.record_id]
            for item in release.governed_release.active_artifacts
        )
        if release is not None
        else ()
    )
    return LongitudinalSimulationReport(
        generated_at=_BASE + timedelta(days=2, minutes=220),
        simulated_dates=tuple(
            sorted({item.created_at.date() for item in simulation.ledger.learning_cycles()})
        ),
        interaction_count=gate.eligible_interaction_count,
        activation_count=gate.activation_count,
        security_probe_count=2,
        final_generation=simulation.state.generation,
        final_active_aliases=final_active_aliases,
        pack_bytes_by_activation=gate.pack_bytes_by_activation,
        latest_pack_utf8_bytes=gate.pack_bytes_by_activation[-1],
        maximum_pack_utf8_bytes=max(gate.pack_bytes_by_activation),
        activations=tuple(simulation.activation_probes),
        simulated_gate=gate,
        checks=checks,
        simulated_product_gate_passed=checks.passed,
    )


def run_longitudinal_simulation(workspace: Path) -> LongitudinalSimulationReport:
    """Run the frozen scenario in an ephemeral directory and return only a raw-free report."""

    workspace.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="temper-longitudinal-", dir=workspace) as temporary:
        temporary_path = Path(temporary)
        report = _run_isolated(temporary_path)
    if temporary_path.exists():
        raise RuntimeError("synthetic longitudinal state was not destroyed")
    return report
