"""Deterministic JSON Schema bundle for automatic-runtime contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.automatic_runtime.gate import CodexDogfoodGateReport
from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    ChangeApplicationReceipt,
    CredentialEnvelopeMetadata,
    CredentialEnvelopeMetadataV1_1,
    GatewayInstrumentMetrics,
    GatewaySession,
    GatewayTurnReceipt,
    NotificationInboxEntry,
    RuntimeNotificationReceipt,
    RuntimeSuccessorReceipt,
    RuntimeWatcherHeartbeat,
    RuntimeWatcherLease,
    VerificationCommandSpec,
    VerificationReceipt,
    WorkspaceBaseline,
    WorkspaceChangeReceipt,
    WorkspaceFileChange,
    WorkspaceLease,
)
from adaptation_compiler_lab.automatic_runtime.longitudinal_simulation import (
    LongitudinalSimulationActivation,
    LongitudinalSimulationChecks,
    LongitudinalSimulationReport,
)
from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRenderedMaterial,
    AutomaticRuntimeMetrics,
    AutomaticRuntimeState,
    CapabilityPresetRef,
    CodexProjectRegistration,
    ComposedRuntimeRelease,
    RuntimeActivationFeedback,
    RuntimeCycleReceipt,
    RuntimeDeliveryReceipt,
    RuntimeLearningAssessment,
    RuntimeLearningCycleReceipt,
    RuntimeLearningReviewResolution,
    RuntimeReviewQueueItem,
    RuntimeReviewScopeRefinement,
    RuntimeSourceCheckpoint,
    RuntimeTargetDeliveryAcknowledgement,
    RuntimeTaskActivationReceipt,
    SemanticInterpreterReceipt,
    StandingAutomationPolicy,
)
from adaptation_compiler_lab.automatic_runtime.product_dogfood import (
    ActivationFeedbackCard,
    ActiveAdaptationCard,
    GateAllowanceCard,
    ReviewModeDogfoodMetrics,
    ReviewModeDogfoodSnapshot,
    ReviewProposalCard,
    TerminalAlphaSnapshot,
)
from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticCorpusAdjudication,
    SemanticEvaluationReport,
    SemanticFeedbackCorpus,
)
from adaptation_compiler_lab.automatic_runtime.semantic_feature_benchmark import (
    SemanticFeatureBlindAudit,
    SemanticFeatureGeneration,
    SemanticFeaturePlan,
    SemanticFeatureProtocol,
    SemanticFeatureRemediation,
    SemanticFeatureSummary,
)
from adaptation_compiler_lab.automatic_runtime.semantic_route_benchmark import (
    SemanticRouteBlindAudit,
    SemanticRouteGeneration,
    SemanticRoutePlan,
    SemanticRouteProtocol,
    SemanticRouteSummary,
)
from adaptation_compiler_lab.automatic_runtime.semantic_stimulation import (
    SemanticStimulationAuditProposal,
    SemanticStimulationGeneration,
    SemanticStimulationIncrementalAudit,
    SemanticStimulationPlan,
    SemanticStimulationProtocol,
    SemanticStimulationRemediation,
    SemanticStimulationSummary,
)

_MODELS: dict[str, type[BaseModel]] = {
    "automatic_rendered_material": AutomaticRenderedMaterial,
    "automatic_runtime_metrics": AutomaticRuntimeMetrics,
    "automatic_runtime_state": AutomaticRuntimeState,
    "activation_feedback_card": ActivationFeedbackCard,
    "active_adaptation_card": ActiveAdaptationCard,
    "capability_preset_ref": CapabilityPresetRef,
    "codex_project_registration": CodexProjectRegistration,
    "codex_dogfood_gate_report": CodexDogfoodGateReport,
    "composed_runtime_release": ComposedRuntimeRelease,
    "credential_envelope_metadata": CredentialEnvelopeMetadata,
    "credential_envelope_metadata_v1_1": CredentialEnvelopeMetadataV1_1,
    "change_application_receipt": ChangeApplicationReceipt,
    "gateway_session": GatewaySession,
    "gateway_instrument_metrics": GatewayInstrumentMetrics,
    "gateway_turn_receipt": GatewayTurnReceipt,
    "gate_allowance_card": GateAllowanceCard,
    "longitudinal_simulation_activation": LongitudinalSimulationActivation,
    "longitudinal_simulation_checks": LongitudinalSimulationChecks,
    "longitudinal_simulation_report": LongitudinalSimulationReport,
    "notification_inbox_entry": NotificationInboxEntry,
    "runtime_cycle_receipt": RuntimeCycleReceipt,
    "runtime_delivery_receipt": RuntimeDeliveryReceipt,
    "runtime_learning_assessment": RuntimeLearningAssessment,
    "runtime_learning_cycle_receipt": RuntimeLearningCycleReceipt,
    "runtime_learning_review_resolution": RuntimeLearningReviewResolution,
    "runtime_review_queue_item": RuntimeReviewQueueItem,
    "runtime_review_scope_refinement": RuntimeReviewScopeRefinement,
    "runtime_notification_receipt": RuntimeNotificationReceipt,
    "runtime_successor_receipt": RuntimeSuccessorReceipt,
    "runtime_watcher_heartbeat": RuntimeWatcherHeartbeat,
    "runtime_watcher_lease": RuntimeWatcherLease,
    "semantic_interpreter_receipt": SemanticInterpreterReceipt,
    "review_mode_dogfood_metrics": ReviewModeDogfoodMetrics,
    "review_mode_dogfood_snapshot": ReviewModeDogfoodSnapshot,
    "review_proposal_card": ReviewProposalCard,
    "terminal_alpha_snapshot": TerminalAlphaSnapshot,
    "semantic_corpus_adjudication": SemanticCorpusAdjudication,
    "semantic_evaluation_report": SemanticEvaluationReport,
    "semantic_feedback_corpus": SemanticFeedbackCorpus,
    "semantic_feature_blind_audit": SemanticFeatureBlindAudit,
    "semantic_feature_generation": SemanticFeatureGeneration,
    "semantic_feature_plan": SemanticFeaturePlan,
    "semantic_feature_protocol": SemanticFeatureProtocol,
    "semantic_feature_remediation": SemanticFeatureRemediation,
    "semantic_feature_summary": SemanticFeatureSummary,
    "semantic_route_blind_audit": SemanticRouteBlindAudit,
    "semantic_route_generation": SemanticRouteGeneration,
    "semantic_route_plan": SemanticRoutePlan,
    "semantic_route_protocol": SemanticRouteProtocol,
    "semantic_route_summary": SemanticRouteSummary,
    "semantic_stimulation_audit_proposal": SemanticStimulationAuditProposal,
    "semantic_stimulation_generation": SemanticStimulationGeneration,
    "semantic_stimulation_incremental_audit": SemanticStimulationIncrementalAudit,
    "semantic_stimulation_plan": SemanticStimulationPlan,
    "semantic_stimulation_protocol": SemanticStimulationProtocol,
    "semantic_stimulation_remediation": SemanticStimulationRemediation,
    "semantic_stimulation_summary": SemanticStimulationSummary,
    "runtime_source_checkpoint": RuntimeSourceCheckpoint,
    "runtime_target_delivery_acknowledgement": RuntimeTargetDeliveryAcknowledgement,
    "runtime_task_activation_receipt": RuntimeTaskActivationReceipt,
    "runtime_activation_feedback": RuntimeActivationFeedback,
    "standing_automation_policy": StandingAutomationPolicy,
    "verification_command_spec": VerificationCommandSpec,
    "verification_receipt": VerificationReceipt,
    "workspace_baseline": WorkspaceBaseline,
    "workspace_change_receipt": WorkspaceChangeReceipt,
    "workspace_file_change": WorkspaceFileChange,
    "workspace_lease": WorkspaceLease,
}


def automatic_runtime_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_automatic_runtime_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in automatic_runtime_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
