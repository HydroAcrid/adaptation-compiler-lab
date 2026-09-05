"""Lazy public API for the governed automatic adaptation runtime.

The desktop engine imports a few runtime submodules directly. Lazy exports keep simulations, CLI
adapters, and unrelated host integrations out of the packaged sidecar startup path.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adaptation_compiler_lab.automatic_runtime.compiler import (
        AutomaticRuntimeCompilerError,
        compile_runtime_release,
        compile_runtime_releases,
    )
    from adaptation_compiler_lab.automatic_runtime.detector import (
        detect_explicit_feedback,
        detect_feedback,
    )
    from adaptation_compiler_lab.automatic_runtime.feedback import summarize_runtime
    from adaptation_compiler_lab.automatic_runtime.gate import (
        CodexDogfoodGateFreezeReceipt,
        CodexDogfoodGateReport,
        build_codex_dogfood_gate_report,
        freeze_codex_dogfood_gate,
    )
    from adaptation_compiler_lab.automatic_runtime.gateway_models import (
        ChangeApplicationReceipt,
        ChangeApplicationStatus,
        CredentialEnvelopeMetadata,
        CredentialEnvelopeMetadataV1_1,
        GatewayInstrumentMetrics,
        GatewaySession,
        GatewaySessionStatus,
        GatewayTurnReceipt,
        NotificationInboxEntry,
        RuntimeNotificationReceipt,
        RuntimeWatcherHeartbeat,
        RuntimeWatcherLease,
        VerificationCommandSpec,
        VerificationReceipt,
        WorkspaceBaseline,
        WorkspaceChangeReceipt,
        WorkspaceFileChange,
        WorkspaceLease,
    )
    from adaptation_compiler_lab.automatic_runtime.host import (
        AutomaticRuntimeHost,
        RuntimeDeliverySink,
        RuntimeHostBatch,
        RuntimeHostRunReceipt,
        RuntimeHostWorkItem,
        RuntimeInteractionSource,
        RuntimeNoticeSink,
        RuntimeReviewSink,
    )
    from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
    from adaptation_compiler_lab.automatic_runtime.longitudinal_simulation import (
        LongitudinalSimulationActivation,
        LongitudinalSimulationChecks,
        LongitudinalSimulationReport,
        run_longitudinal_simulation,
    )
    from adaptation_compiler_lab.automatic_runtime.models import (
        AdaptationLayer,
        AutomaticRenderedMaterial,
        AutomaticRuntimeMetrics,
        AutomaticRuntimeState,
        AutomationDisposition,
        CapabilityPresetRef,
        CapturedInteraction,
        CodexProjectRegistration,
        ComposedRuntimeRelease,
        DetectedFeedback,
        ExternalProposalOriginV1,
        FeedbackDetectorMode,
        FeedbackSignalKind,
        InteractionObservation,
        PreparedRuntimeActivation,
        PreparedRuntimeTask,
        RuntimeActivationFeedback,
        RuntimeCycleReceipt,
        RuntimeDeliveryReceipt,
        RuntimeEvaluationReceipt,
        RuntimeExternalAdoptionResolution,
        RuntimeFeedbackOutcome,
        RuntimeLayerBinding,
        RuntimeLearningAssessment,
        RuntimeLearningAssessmentOutcome,
        RuntimeLearningCycleReceipt,
        RuntimeLearningReviewResolution,
        RuntimeLearningTransition,
        RuntimeNotice,
        RuntimeNoticeKind,
        RuntimeReviewQueueItem,
        RuntimeReviewScopeRefinement,
        RuntimeSourceCheckpoint,
        RuntimeTargetDeliveryAcknowledgement,
        RuntimeTaskActivationReceipt,
        RuntimeTransitionKind,
        SemanticAssertionKind,
        SemanticExampleIntent,
        SemanticFeatureVector,
        SemanticFeedbackInterpretation,
        SemanticFeedbackSignal,
        SemanticInterpreterReceipt,
        SemanticNormStrength,
        SemanticRouteResolution,
        SemanticScopeHint,
        SemanticSignalClarity,
        SemanticSignalDurability,
        SemanticTransitionIntent,
        SemanticWorkflowStructure,
        StandingAutomationPolicy,
        infer_layer,
    )
    from adaptation_compiler_lab.automatic_runtime.product_dogfood import (
        ActivationFeedbackCard,
        ActiveAdaptationCard,
        GateAllowanceCard,
        ReviewModeDogfoodMetrics,
        ReviewModeDogfoodSnapshot,
        ReviewProposalCard,
        TerminalAlphaSnapshot,
        build_review_mode_dogfood_snapshot,
        build_terminal_alpha_snapshot,
    )
    from adaptation_compiler_lab.automatic_runtime.service import (
        AutomaticAdaptationRuntime,
        AutomaticExternalAdoptionResult,
        AutomaticLearningResult,
        AutomaticReviewResolutionResult,
        AutomaticRuntimeError,
        AutomaticRuntimeResult,
        initial_runtime_state,
    )

_LAZY_EXPORTS: dict[str, str] = {}


def _register(module: str, names: tuple[str, ...]) -> None:
    for name in names:
        _LAZY_EXPORTS[name] = module


_register(
    "adaptation_compiler_lab.automatic_runtime.compiler",
    ("AutomaticRuntimeCompilerError", "compile_runtime_release", "compile_runtime_releases"),
)
_register(
    "adaptation_compiler_lab.automatic_runtime.detector",
    ("detect_explicit_feedback", "detect_feedback"),
)
_register("adaptation_compiler_lab.automatic_runtime.feedback", ("summarize_runtime",))
_register(
    "adaptation_compiler_lab.automatic_runtime.gate",
    (
        "CodexDogfoodGateFreezeReceipt",
        "CodexDogfoodGateReport",
        "build_codex_dogfood_gate_report",
        "freeze_codex_dogfood_gate",
    ),
)
_register(
    "adaptation_compiler_lab.automatic_runtime.gateway_models",
    (
        "ChangeApplicationReceipt",
        "ChangeApplicationStatus",
        "CredentialEnvelopeMetadata",
        "CredentialEnvelopeMetadataV1_1",
        "GatewayInstrumentMetrics",
        "GatewaySession",
        "GatewaySessionStatus",
        "GatewayTurnReceipt",
        "NotificationInboxEntry",
        "RuntimeNotificationReceipt",
        "RuntimeWatcherHeartbeat",
        "RuntimeWatcherLease",
        "VerificationCommandSpec",
        "VerificationReceipt",
        "WorkspaceBaseline",
        "WorkspaceChangeReceipt",
        "WorkspaceFileChange",
        "WorkspaceLease",
    ),
)
_register(
    "adaptation_compiler_lab.automatic_runtime.host",
    (
        "AutomaticRuntimeHost",
        "RuntimeDeliverySink",
        "RuntimeHostBatch",
        "RuntimeHostRunReceipt",
        "RuntimeHostWorkItem",
        "RuntimeInteractionSource",
        "RuntimeNoticeSink",
        "RuntimeReviewSink",
    ),
)
_register("adaptation_compiler_lab.automatic_runtime.ledger", ("AutomaticRuntimeLedger",))
_register(
    "adaptation_compiler_lab.automatic_runtime.longitudinal_simulation",
    (
        "LongitudinalSimulationActivation",
        "LongitudinalSimulationChecks",
        "LongitudinalSimulationReport",
        "run_longitudinal_simulation",
    ),
)
_register(
    "adaptation_compiler_lab.automatic_runtime.models",
    (
        "AdaptationLayer",
        "AutomaticRenderedMaterial",
        "AutomaticRuntimeMetrics",
        "AutomaticRuntimeState",
        "AutomationDisposition",
        "CapabilityPresetRef",
        "CapturedInteraction",
        "CodexProjectRegistration",
        "ComposedRuntimeRelease",
        "DetectedFeedback",
        "ExternalProposalOriginV1",
        "FeedbackDetectorMode",
        "FeedbackSignalKind",
        "InteractionObservation",
        "PreparedRuntimeActivation",
        "PreparedRuntimeTask",
        "RuntimeActivationFeedback",
        "RuntimeCycleReceipt",
        "RuntimeDeliveryReceipt",
        "RuntimeEvaluationReceipt",
        "RuntimeExternalAdoptionResolution",
        "RuntimeFeedbackOutcome",
        "RuntimeLayerBinding",
        "RuntimeLearningAssessment",
        "RuntimeLearningAssessmentOutcome",
        "RuntimeLearningCycleReceipt",
        "RuntimeLearningReviewResolution",
        "RuntimeLearningTransition",
        "RuntimeNotice",
        "RuntimeNoticeKind",
        "RuntimeReviewQueueItem",
        "RuntimeReviewScopeRefinement",
        "RuntimeSourceCheckpoint",
        "RuntimeTargetDeliveryAcknowledgement",
        "RuntimeTaskActivationReceipt",
        "RuntimeTransitionKind",
        "SemanticAssertionKind",
        "SemanticExampleIntent",
        "SemanticFeatureVector",
        "SemanticFeedbackInterpretation",
        "SemanticFeedbackSignal",
        "SemanticInterpreterReceipt",
        "SemanticNormStrength",
        "SemanticRouteResolution",
        "SemanticScopeHint",
        "SemanticSignalClarity",
        "SemanticSignalDurability",
        "SemanticTransitionIntent",
        "SemanticWorkflowStructure",
        "StandingAutomationPolicy",
        "infer_layer",
    ),
)
_register(
    "adaptation_compiler_lab.automatic_runtime.product_dogfood",
    (
        "ActivationFeedbackCard",
        "ActiveAdaptationCard",
        "GateAllowanceCard",
        "ReviewModeDogfoodMetrics",
        "ReviewModeDogfoodSnapshot",
        "ReviewProposalCard",
        "TerminalAlphaSnapshot",
        "build_review_mode_dogfood_snapshot",
        "build_terminal_alpha_snapshot",
    ),
)
_register(
    "adaptation_compiler_lab.automatic_runtime.service",
    (
        "AutomaticAdaptationRuntime",
        "AutomaticExternalAdoptionResult",
        "AutomaticLearningResult",
        "AutomaticReviewResolutionResult",
        "AutomaticRuntimeError",
        "AutomaticRuntimeResult",
        "initial_runtime_state",
    ),
)

__all__ = [
    "ActivationFeedbackCard",
    "ActiveAdaptationCard",
    "AdaptationLayer",
    "AutomaticAdaptationRuntime",
    "AutomaticExternalAdoptionResult",
    "AutomaticLearningResult",
    "AutomaticRenderedMaterial",
    "AutomaticReviewResolutionResult",
    "AutomaticRuntimeCompilerError",
    "AutomaticRuntimeError",
    "AutomaticRuntimeHost",
    "AutomaticRuntimeLedger",
    "AutomaticRuntimeMetrics",
    "AutomaticRuntimeResult",
    "AutomaticRuntimeState",
    "AutomationDisposition",
    "CapabilityPresetRef",
    "CapturedInteraction",
    "ChangeApplicationReceipt",
    "ChangeApplicationStatus",
    "CodexDogfoodGateFreezeReceipt",
    "CodexDogfoodGateReport",
    "CodexProjectRegistration",
    "ComposedRuntimeRelease",
    "CredentialEnvelopeMetadata",
    "CredentialEnvelopeMetadataV1_1",
    "DetectedFeedback",
    "ExternalProposalOriginV1",
    "FeedbackDetectorMode",
    "FeedbackSignalKind",
    "GateAllowanceCard",
    "GatewayInstrumentMetrics",
    "GatewaySession",
    "GatewaySessionStatus",
    "GatewayTurnReceipt",
    "InteractionObservation",
    "LongitudinalSimulationActivation",
    "LongitudinalSimulationChecks",
    "LongitudinalSimulationReport",
    "NotificationInboxEntry",
    "PreparedRuntimeActivation",
    "PreparedRuntimeTask",
    "ReviewModeDogfoodMetrics",
    "ReviewModeDogfoodSnapshot",
    "ReviewProposalCard",
    "RuntimeActivationFeedback",
    "RuntimeCycleReceipt",
    "RuntimeDeliveryReceipt",
    "RuntimeDeliverySink",
    "RuntimeEvaluationReceipt",
    "RuntimeExternalAdoptionResolution",
    "RuntimeFeedbackOutcome",
    "RuntimeHostBatch",
    "RuntimeHostRunReceipt",
    "RuntimeHostWorkItem",
    "RuntimeInteractionSource",
    "RuntimeLayerBinding",
    "RuntimeLearningAssessment",
    "RuntimeLearningAssessmentOutcome",
    "RuntimeLearningCycleReceipt",
    "RuntimeLearningReviewResolution",
    "RuntimeLearningTransition",
    "RuntimeNotice",
    "RuntimeNoticeKind",
    "RuntimeNoticeSink",
    "RuntimeNotificationReceipt",
    "RuntimeReviewQueueItem",
    "RuntimeReviewScopeRefinement",
    "RuntimeReviewSink",
    "RuntimeSourceCheckpoint",
    "RuntimeTargetDeliveryAcknowledgement",
    "RuntimeTaskActivationReceipt",
    "RuntimeTransitionKind",
    "RuntimeWatcherHeartbeat",
    "RuntimeWatcherLease",
    "SemanticAssertionKind",
    "SemanticExampleIntent",
    "SemanticFeatureVector",
    "SemanticFeedbackInterpretation",
    "SemanticFeedbackSignal",
    "SemanticInterpreterReceipt",
    "SemanticNormStrength",
    "SemanticRouteResolution",
    "SemanticScopeHint",
    "SemanticSignalClarity",
    "SemanticSignalDurability",
    "SemanticTransitionIntent",
    "SemanticWorkflowStructure",
    "StandingAutomationPolicy",
    "TerminalAlphaSnapshot",
    "VerificationCommandSpec",
    "VerificationReceipt",
    "WorkspaceBaseline",
    "WorkspaceChangeReceipt",
    "WorkspaceFileChange",
    "WorkspaceLease",
    "build_codex_dogfood_gate_report",
    "build_review_mode_dogfood_snapshot",
    "build_terminal_alpha_snapshot",
    "compile_runtime_release",
    "compile_runtime_releases",
    "detect_explicit_feedback",
    "detect_feedback",
    "freeze_codex_dogfood_gate",
    "infer_layer",
    "initial_runtime_state",
    "run_longitudinal_simulation",
    "summarize_runtime",
]

assert set(__all__) == set(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    """Load one explicitly exported runtime API only when requested."""

    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
