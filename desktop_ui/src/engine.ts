import { invoke } from "@tauri-apps/api/core";

import type { CapabilityModeSummary, PortableProfilePreview } from "./types";

export const ENGINE_PROTOCOL_VERSION = "temper-engine-protocol/v1" as const;

export interface EngineError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface EngineClientFailure {
  code: string;
  message: string;
}

const knownClientFailures: Record<string, string> = {
  cancelled: "Nothing changed.",
  engine_incompatible:
    "The desktop app and its local engine do not match. Reinstall this Temper build.",
  engine_unavailable:
    "The local engine stopped unexpectedly. Try again; reinstall Temper if this continues.",
};

export function normalizeEngineFailure(
  error: unknown,
  fallback = "The local Temper engine is unavailable.",
): EngineClientFailure {
  if (error && typeof error === "object") {
    const candidate = error as { code?: unknown; message?: unknown };
    const code =
      typeof candidate.code === "string" && candidate.code.length <= 64
        ? candidate.code
        : "engine_error";
    const known = knownClientFailures[code];
    if (known) return { code, message: known };
    if (
      typeof candidate.message === "string" &&
      candidate.message.trim() &&
      candidate.message.length <= 240 &&
      !candidate.message.includes("\n")
    ) {
      return { code, message: candidate.message.trim() };
    }
  }
  if (
    error instanceof Error &&
    error.message.trim() &&
    error.message.length <= 240 &&
    !error.message.includes("\n")
  ) {
    return { code: "engine_error", message: error.message.trim() };
  }
  return { code: "engine_error", message: fallback };
}

export function engineFailureMessage(
  error: unknown,
  fallback?: string,
): string {
  return normalizeEngineFailure(error, fallback).message;
}

export interface EngineResponse<T> {
  protocol_version: typeof ENGINE_PROTOCOL_VERSION;
  request_id: string;
  ok: boolean;
  result: T | null;
  error: EngineError | null;
  snapshot_digest: string | null;
}

export interface EngineHandshake {
  protocol_version: typeof ENGINE_PROTOCOL_VERSION;
  engine_version: string;
  snapshot_schema_digest: string;
  mutation_enabled: boolean;
  configured: boolean;
  setup_available: true;
  configuration_state: "unconfigured" | "configured";
  platform: "windows" | "macos" | "development";
  architecture: string;
}

export interface EngineAgentConnection {
  connection_version: "1.0.0";
  agent_id: "codex" | "claude";
  display_name: "Codex" | "Claude Code";
  installation_state: "not_installed" | "installed";
  authentication_state: "unknown" | "signed_out" | "signed_in";
  conformance_state:
    "not_applicable" | "unverified" | "compatible" | "update_required";
  version_label: string | null;
  status_summary: string;
  learning_capability: string;
  delivery_capability: string;
  cost_posture: string;
  available_actions: Array<"refresh" | "use_for_setup">;
  raw_payloads_exposed: false;
}

export interface EngineSetupSnapshot {
  setup_version: "1.0.0";
  product_name: "Temper";
  configuration_state:
    "unconfigured" | "existing_available" | "configured" | "incompatible";
  secure_store: {
    platform: "windows" | "macos" | "development";
    protector:
      | "windows-dpapi-current-user"
      | "macos-keychain-current-user"
      | "unavailable";
    status: "not_created" | "ready" | "locked" | "unavailable";
  };
  connections: [EngineAgentConnection, EngineAgentConnection];
  existing_installation: {
    signer_fingerprint: string;
    project_count: number;
    consent_expires_at: string;
    secure_store_ready: boolean;
  } | null;
  learning_enabled: false;
  automatic_promotion_enabled: false;
  aggregate_reporting_enabled: false;
  launch_at_login_enabled: false;
  raw_payloads_exposed: false;
}

export type EngineExistingInstallation = NonNullable<
  EngineSetupSnapshot["existing_installation"]
>;

export interface EngineExistingInstallationPreview {
  preview_token: string;
  installation: EngineExistingInstallation;
  raw_payloads_exposed: false;
}

export interface EngineProjectPreview {
  preview_version: "1.0.0";
  preview_token: string;
  project_id: string;
  display_name: string;
  capture_after_epoch_seconds: number;
  historical_tasks_eligible: false;
  modifies_existing_tasks: false;
  modifies_repository: false;
  expires_at: string;
}

export interface EngineProject {
  project_id: string;
  display_name: string;
  registered_prospectively: boolean;
  task_runner_enabled: boolean;
}

export type EngineNativeTarget = "codex" | "claude" | "copilot";

export interface EngineInstructionSourceSummary {
  summary_version: "1.0.0";
  source_id: string;
  target: EngineNativeTarget;
  kind:
    | "project_instructions"
    | "project_rule"
    | "project_skill"
    | "personal_instructions"
    | "personal_memory"
    | "personal_skill"
    | "managed_instructions";
  display_path: string;
  scope_summary: string;
  status:
    | "ready"
    | "unreadable"
    | "invalid_encoding"
    | "too_large"
    | "outside_boundary"
    | "unsupported";
  instruction_count: number;
  skill: boolean;
  activation_status:
    "active" | "available" | "disabled" | "unknown" | "not_applicable";
  observed_context_only: true;
  raw_payloads_exposed: false;
}

export interface EngineInstructionEnvironmentSummary {
  summary_version: "1.0.0";
  project_id: string;
  target: EngineNativeTarget;
  status: "understood" | "changed" | "incomplete" | "conflicting";
  source_count: number;
  skill_count: number;
  instruction_count: number;
  blocking_conflict_count: number;
  semantic_analysis_status:
    "not_requested" | "current" | "stale" | "unavailable";
  last_analyzed_at: string;
  environment_digest: string;
  source_chain_digest: string;
  surface?: string;
  surface_contract_version?: string;
  global_sources_enabled: boolean;
  sources: EngineInstructionSourceSummary[];
  conflicts?: Array<{
    summary_version: "1.0.0";
    conflict_id: string;
    project_id: string;
    target: EngineNativeTarget;
    source_display_path: string;
    temper_behavior: string;
    native_behavior: string;
    severity: "notice" | "blocking";
    resolution_state:
      "unresolved" | "kept_native" | "narrowed_temper" | "ignored";
    rationale: string;
    raw_payloads_exposed: false;
  }>;
  raw_payloads_exposed: false;
}

export interface EngineInstructionEnvironmentList {
  environments: EngineInstructionEnvironmentSummary[];
  raw_payloads_exposed: false;
}

export interface EngineInstructionGlobalPreview {
  preview_version: "1.0.0";
  preview_token: string;
  target: EngineNativeTarget;
  categories: string[];
  source_count: number;
  skill_count: number;
  modifies_files: false;
  authorizes_learning: false;
  expires_at: string;
  raw_payloads_exposed: false;
}

export interface EngineInstructionChangePreview {
  preview_version: "1.0.0";
  preview_token: string;
  project_id: string;
  target: EngineNativeTarget;
  source_id: string;
  source_digest: string;
  expected_environment_digest: string;
  operation:
    "create_temper_section" | "update_temper_section" | "remove_temper_section";
  display_path: string;
  unified_diff: string;
  resulting_digest: string;
  expires_at: string;
  raw_payloads_exposed: false;
}

export interface EngineInstructionChangeReceipt {
  receipt_version: "1.0.0";
  receipt_id: string;
  preview_token: string;
  project_id: string;
  target: EngineNativeTarget;
  source_id: string;
  before_digest: string;
  after_digest: string;
  environment_digest_before: string;
  environment_digest_after: string;
  backup_digest: string;
  applied_at: string;
  signer_fingerprint: string;
  signature_base64: string;
  rollback_available_until: string;
  status: "applied" | "rolled_back";
  raw_payloads_exposed: false;
}

export interface EngineScope {
  subject_ids: string[];
  workspace_ids: string[];
  project_ids: string[];
  repository_ids: string[];
  task_classes: string[];
  target_families: string[];
  environment_ids: string[];
  activation_conditions: string[];
  exclusions: string[];
  valid_from: string | null;
  valid_until: string | null;
}

export interface EngineSuggestion {
  summary_version: "1.0.0";
  review_number: number;
  queue_id: string;
  proposal_digest: string;
  signal_kind: string;
  proposed_behavior: string | null;
  affected_artifact_id: string | null;
  route: string | null;
  layer: string;
  suggested_scope: EngineScope;
  reason_summary: string[];
  evidence_digest: string;
  consent_digest: string;
  capture_digest: string;
  available_actions: EngineSuggestionDecision[];
  created_at: string;
  raw_payloads_exposed: false;
}

export type EngineSuggestionDecision =
  | "keep_suggested"
  | "keep_project"
  | "keep_narrowed"
  | "ignore"
  | "approve_revocation"
  | "reject_revocation";

export interface EngineAdaptation {
  summary_version: "1.0.0";
  artifact_id: string;
  artifact_version: string;
  artifact_digest: string;
  artifact_type: string;
  layer: string;
  intent: string;
  required_behaviors: string[];
  scope: EngineScope;
  evidence_count: number;
  review_at: string | null;
  expires_at: string | null;
  available_actions: ["revoke"];
  raw_payloads_exposed: false;
}

export interface EngineActivationFeedback {
  summary_version: "1.0.0";
  activation_id: string;
  delivery_receipt_digest: string;
  active_artifact_ids: string[];
  projection_utf8_bytes: number;
  activated_at: string;
  completed_at: string;
  available_outcomes: Array<"helped" | "hurt" | "irrelevant">;
  raw_payloads_exposed: false;
}

export interface EngineRecentUndo {
  summary_version: "1.0.0";
  notice_id: string;
  notice_digest: string;
  artifact_id: string;
  summary: string;
  created_at: string;
  expires_at: string;
  raw_payloads_exposed: false;
}

export interface EngineMutationReceipt {
  receipt_version: "1.0.0";
  action: string;
  target_id: string;
  status: "applied";
  code: string;
  message: string;
  resulting_snapshot_digest: string;
  raw_payloads_exposed: false;
}

export interface EngineDesktopSnapshot {
  snapshot_version: "1.1.0";
  product_name: "Temper";
  health: "ready" | "needs_attention" | "paused" | "consent_expired";
  background_enabled: boolean;
  aggregate_reporting_enabled: boolean;
  decision_notifications_enabled: boolean;
  launch_at_login_enabled: boolean;
  projects: EngineProject[];
  generated_at: string;
  raw_payloads_exposed: false;
  consent: {
    effective_at: string;
    expires_at: string;
    retention_days: number;
    days_remaining: number;
    renewal_required: boolean;
  };
  suggestions: EngineSuggestion[];
  adaptations: EngineAdaptation[];
  activation_feedback: EngineActivationFeedback[];
  recent_undos: EngineRecentUndo[];
  terminal: {
    review_mode: {
      active_artifact_count: number;
      proposals: EngineTerminalProposal[];
      activation_feedback: EngineTerminalActivationFeedback[];
      metrics: {
        pending_review_count: number;
        pending_feedback_count: number;
      };
    };
    active_adaptations: Array<{
      artifact_id: string;
      artifact_version: string;
      artifact_type: string;
      layer: string;
      intent: string;
      required_behaviors: string[];
      scope: {
        project_ids: string[];
        task_classes: string[];
        target_families: string[];
        environment_ids: string[];
      };
      evidence_count: number;
      raw_payload_exposed: false;
    }>;
    latest_delivered_projection_utf8_bytes: number;
    raw_payloads_exposed: false;
  };
}

export interface EngineTerminalProposal {
  card_version: "1.1.0";
  review_number: number;
  queue_id: string;
  cycle_id: string;
  proposal_digest: string;
  signal_kind: string;
  behavior: string | null;
  affected_artifact_id: string | null;
  route: string | null;
  layer: string;
  scope: EngineScope;
  reasons: string[];
  available_actions: Array<"approve" | "reject" | "refine_scope">;
  created_at: string;
  raw_payload_exposed: false;
}

export interface EngineTerminalActivationFeedback {
  card_version: "1.0.0";
  activation_id: string;
  task_ref_id: string;
  delivery_receipt_digest: string;
  active_artifact_ids: string[];
  projection_utf8_bytes: number;
  activated_at: string;
  completed_at: string;
  available_actions: Array<"helped" | "hurt" | "irrelevant">;
  raw_payload_exposed: false;
}

async function invokeMutation(
  command: string,
  args: Record<string, unknown>,
): Promise<EngineMutationReceipt> {
  const receipt = assertSuccessful(
    await invoke<EngineResponse<EngineMutationReceipt>>(command, args),
  );
  if (receipt.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe mutation receipt.");
  }
  return receipt;
}

export async function pollLearning(
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("learning_poll", {
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
  });
}

export async function decideEngineSuggestion(
  suggestion: EngineSuggestion,
  decision: EngineSuggestionDecision,
  snapshotDigest: string,
  idempotencyKey: string,
  options: { projectId?: string; refinedScope?: EngineScope } = {},
): Promise<EngineMutationReceipt> {
  return invokeMutation("review_decide", {
    decision,
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
    projectId: options.projectId ?? null,
    proposalDigest: suggestion.proposal_digest,
    queueId: suggestion.queue_id,
    refinedScope: options.refinedScope ?? null,
  });
}

export async function revokeEngineAdaptation(
  adaptation: EngineAdaptation,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("adaptation_revoke", {
    artifactDigest: adaptation.artifact_digest,
    artifactId: adaptation.artifact_id,
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
  });
}

export async function undoEngineAdaptation(
  undo: EngineRecentUndo,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("adaptation_undo", {
    artifactId: undo.artifact_id,
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
    noticeDigest: undo.notice_digest,
    noticeId: undo.notice_id,
  });
}

export async function recordEngineFeedback(
  activation: EngineActivationFeedback,
  outcome: "helped" | "hurt" | "irrelevant",
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("feedback_record", {
    activationId: activation.activation_id,
    deliveryReceiptDigest: activation.delivery_receipt_digest,
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
    outcome,
  });
}

export async function renewEngineConsent(
  currentExpiresAt: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("consent_renew", {
    currentExpiresAt,
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
  });
}

export async function updateEnginePreferences(
  backgroundEnabled: boolean,
  aggregateReportingEnabled: boolean,
  decisionNotificationsEnabled: boolean,
  launchAtLoginEnabled: boolean,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("preferences_update", {
    preferences: {
      aggregateReportingEnabled,
      backgroundEnabled,
      decisionNotificationsEnabled,
      launchAtLoginEnabled,
    },
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
  });
}

export type NotificationPermissionState =
  "granted" | "denied" | "prompt" | "prompt-with-rationale";

export async function requestNotificationPermission(): Promise<NotificationPermissionState> {
  return invoke<NotificationPermissionState>("notification_permission", {
    request: true,
  });
}

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

function assertSuccessful<T>(response: EngineResponse<T>): T {
  if (response.protocol_version !== ENGINE_PROTOCOL_VERSION) {
    throw new Error("Temper's desktop and local engine versions do not match.");
  }
  if (!response.ok || response.result === null) {
    throw new Error(
      response.error?.message ?? "The local Temper engine is unavailable.",
    );
  }
  return response.result;
}

export async function loadEngineSnapshot(): Promise<{
  handshake: EngineHandshake;
  snapshot: EngineDesktopSnapshot;
  snapshotDigest: string;
}> {
  const handshakeResponse =
    await invoke<EngineResponse<EngineHandshake>>("engine_handshake");
  const handshake = assertSuccessful(handshakeResponse);
  if (!handshake.configured) {
    throw new Error(
      "Temper needs a governed local setup before it can load your work.",
    );
  }
  const snapshotResponse =
    await invoke<EngineResponse<EngineDesktopSnapshot>>("snapshot_get");
  const snapshot = assertSuccessful(snapshotResponse);
  if (snapshot.raw_payloads_exposed || snapshot.terminal.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe desktop snapshot.");
  }
  if (!snapshotResponse.snapshot_digest) {
    throw new Error("Temper could not bind the desktop snapshot.");
  }
  return {
    handshake,
    snapshot,
    snapshotDigest: snapshotResponse.snapshot_digest,
  };
}

export async function loadEngineHandshake(): Promise<EngineHandshake> {
  return assertSuccessful(
    await invoke<EngineResponse<EngineHandshake>>("engine_handshake"),
  );
}

export async function loadSetupSnapshot(): Promise<{
  snapshot: EngineSetupSnapshot;
  snapshotDigest: string;
}> {
  const response =
    await invoke<EngineResponse<EngineSetupSnapshot>>("setup_status");
  const snapshot = assertSuccessful(response);
  if (snapshot.raw_payloads_exposed || !response.snapshot_digest) {
    throw new Error("Temper refused an unsafe setup state.");
  }
  return { snapshot, snapshotDigest: response.snapshot_digest };
}

export async function inspectConnections(): Promise<{
  snapshot: EngineSetupSnapshot;
  snapshotDigest: string;
}> {
  const response =
    await invoke<EngineResponse<EngineSetupSnapshot>>("connection_inspect");
  const snapshot = assertSuccessful(response);
  if (snapshot.raw_payloads_exposed || !response.snapshot_digest) {
    throw new Error("Temper refused an unsafe connection state.");
  }
  return { snapshot, snapshotDigest: response.snapshot_digest };
}

export async function previewSetupProject(): Promise<EngineProjectPreview | null> {
  const response = await invoke<EngineResponse<EngineProjectPreview>>(
    "setup_project_preview",
  );
  if (
    response.protocol_version === ENGINE_PROTOCOL_VERSION &&
    !response.ok &&
    response.error?.code === "cancelled"
  ) {
    return null;
  }
  return assertSuccessful(response);
}

export async function previewExistingInstallation(): Promise<EngineExistingInstallationPreview | null> {
  const response = await invoke<
    EngineResponse<EngineExistingInstallationPreview>
  >("setup_existing_preview");
  if (
    response.protocol_version === ENGINE_PROTOCOL_VERSION &&
    !response.ok &&
    response.error?.code === "cancelled"
  ) {
    return null;
  }
  const preview = assertSuccessful(response);
  if (preview.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe installation preview.");
  }
  return preview;
}

export async function adoptExistingInstallation(
  previewToken: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<{
  installation: EngineExistingInstallation;
  restart_required: true;
}> {
  return assertSuccessful(
    await invoke<
      EngineResponse<{
        installation: EngineExistingInstallation;
        restart_required: true;
      }>
    >("setup_existing_adopt", {
      expectedSnapshotDigest: snapshotDigest,
      idempotencyKey,
      previewToken,
    }),
  );
}

export async function previewProjectRegistration(): Promise<EngineProjectPreview> {
  return assertSuccessful(
    await invoke<EngineResponse<EngineProjectPreview>>(
      "project_registration_preview",
    ),
  );
}

export async function registerProject(
  previewToken: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<{
  project_id: string;
  display_name: string;
  capture_after_epoch_seconds: number;
  historical_tasks_eligible: false;
}> {
  return assertSuccessful(
    await invoke<
      EngineResponse<{
        project_id: string;
        display_name: string;
        capture_after_epoch_seconds: number;
        historical_tasks_eligible: false;
      }>
    >("project_register", {
      expectedSnapshotDigest: snapshotDigest,
      idempotencyKey,
      previewToken,
    }),
  );
}

function assertRawFreeInstructionEnvironment(
  value: EngineInstructionEnvironmentSummary,
): EngineInstructionEnvironmentSummary {
  if (
    value.raw_payloads_exposed ||
    value.sources.some(
      (source) => source.raw_payloads_exposed || !source.observed_context_only,
    ) ||
    value.conflicts?.some((conflict) => conflict.raw_payloads_exposed)
  ) {
    throw new Error(
      "Temper refused an unsafe instruction-environment summary.",
    );
  }
  return value;
}

export async function loadInstructionEnvironments(): Promise<
  EngineInstructionEnvironmentSummary[]
> {
  const response = assertSuccessful(
    await invoke<EngineResponse<EngineInstructionEnvironmentList>>(
      "instruction_environment_get",
    ),
  );
  if (response.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe instruction-environment list.");
  }
  return response.environments.map(assertRawFreeInstructionEnvironment);
}

export async function refreshInstructionEnvironment(
  projectId: string,
  target: EngineNativeTarget,
): Promise<EngineInstructionEnvironmentSummary> {
  return assertRawFreeInstructionEnvironment(
    assertSuccessful(
      await invoke<EngineResponse<EngineInstructionEnvironmentSummary>>(
        "instruction_environment_refresh",
        { projectId, target },
      ),
    ),
  );
}

export async function analyzeInstructionEnvironment(
  projectId: string,
  target: EngineNativeTarget,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineInstructionEnvironmentSummary> {
  return assertRawFreeInstructionEnvironment(
    assertSuccessful(
      await invoke<EngineResponse<EngineInstructionEnvironmentSummary>>(
        "instruction_environment_analyze",
        {
          expectedSnapshotDigest: snapshotDigest,
          idempotencyKey,
          projectId,
          target,
        },
      ),
    ),
  );
}

export async function previewPersonalInstructionSetup(
  target: EngineNativeTarget,
): Promise<EngineInstructionGlobalPreview | null> {
  const response = await invoke<EngineResponse<EngineInstructionGlobalPreview>>(
    "instruction_environment_global_preview",
    { target },
  );
  if (
    response.protocol_version === ENGINE_PROTOCOL_VERSION &&
    !response.ok &&
    response.error?.code === "cancelled"
  ) {
    return null;
  }
  const preview = assertSuccessful(response);
  if (
    preview.raw_payloads_exposed ||
    preview.modifies_files ||
    preview.authorizes_learning
  ) {
    throw new Error("Temper refused an unsafe personal-setup preview.");
  }
  return preview;
}

export async function enablePersonalInstructionSetup(
  previewToken: string,
  target: EngineNativeTarget,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineInstructionEnvironmentSummary[]> {
  const response = assertSuccessful(
    await invoke<EngineResponse<EngineInstructionEnvironmentList>>(
      "instruction_environment_global_enable",
      {
        expectedSnapshotDigest: snapshotDigest,
        idempotencyKey,
        previewToken,
        target,
      },
    ),
  );
  if (response.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe personal-setup result.");
  }
  return response.environments.map(assertRawFreeInstructionEnvironment);
}

export async function disablePersonalInstructionSetup(
  target: EngineNativeTarget,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineInstructionEnvironmentSummary[]> {
  const response = assertSuccessful(
    await invoke<EngineResponse<EngineInstructionEnvironmentList>>(
      "instruction_environment_global_disable",
      {
        expectedSnapshotDigest: snapshotDigest,
        idempotencyKey,
        target,
      },
    ),
  );
  if (response.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe personal-setup result.");
  }
  return response.environments.map(assertRawFreeInstructionEnvironment);
}

export async function previewNativeInstructionChange(
  environment: EngineInstructionEnvironmentSummary,
  sourceId: string,
  instructionText: string | null,
  snapshotDigest: string,
): Promise<EngineInstructionChangePreview> {
  const preview = assertSuccessful(
    await invoke<EngineResponse<EngineInstructionChangePreview>>(
      "instruction_environment_change_preview",
      {
        expectedEnvironmentDigest: environment.environment_digest,
        expectedSnapshotDigest: snapshotDigest,
        instructionText,
        projectId: environment.project_id,
        sourceId,
        target: environment.target,
      },
    ),
  );
  if (preview.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe native-instruction preview.");
  }
  return preview;
}

export async function applyNativeInstructionChange(
  preview: EngineInstructionChangePreview,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineInstructionChangeReceipt> {
  const receipt = assertSuccessful(
    await invoke<EngineResponse<EngineInstructionChangeReceipt>>(
      "instruction_environment_change_apply",
      {
        expectedEnvironmentDigest: preview.expected_environment_digest,
        expectedSnapshotDigest: snapshotDigest,
        idempotencyKey,
        previewToken: preview.preview_token,
        target: preview.target,
      },
    ),
  );
  if (receipt.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe native-instruction receipt.");
  }
  return receipt;
}

export async function rollbackNativeInstructionChange(
  receipt: EngineInstructionChangeReceipt,
  currentEnvironmentDigest: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineInstructionChangeReceipt> {
  const rolledBack = assertSuccessful(
    await invoke<EngineResponse<EngineInstructionChangeReceipt>>(
      "instruction_environment_change_rollback",
      {
        expectedEnvironmentDigest: currentEnvironmentDigest,
        expectedSnapshotDigest: snapshotDigest,
        idempotencyKey,
        receiptId: receipt.receipt_id,
        target: receipt.target,
      },
    ),
  );
  if (rolledBack.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe native-instruction rollback.");
  }
  return rolledBack;
}

export async function initializeSetup(
  previewToken: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<{
  subject_id: string;
  signer_fingerprint: string;
  project_id: string;
  capture_after_epoch_seconds: number;
  consent_expires_at: string;
}> {
  return assertSuccessful(
    await invoke<
      EngineResponse<{
        subject_id: string;
        signer_fingerprint: string;
        project_id: string;
        capture_after_epoch_seconds: number;
        consent_expires_at: string;
      }>
    >("setup_initialize", {
      consentConfirmed: true,
      expectedSnapshotDigest: snapshotDigest,
      idempotencyKey,
      previewToken,
    }),
  );
}

export interface ProfileExportPreview extends PortableProfilePreview {
  export_token: string;
}

export interface ProfileImportPreview extends PortableProfilePreview {
  import_token: string;
}

export async function loadProfileExportPreview(): Promise<ProfileExportPreview> {
  return assertSuccessful(
    await invoke<EngineResponse<ProfileExportPreview>>(
      "profile_export_preview",
    ),
  );
}

export async function exportProfile(
  preview: ProfileExportPreview,
  passphrase: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<{ status: "exported"; package_digest: string; item_count: number }> {
  return assertSuccessful(
    await invoke<
      EngineResponse<{
        status: "exported";
        package_digest: string;
        item_count: number;
      }>
    >("profile_export", {
      expectedSnapshotDigest: snapshotDigest,
      exportToken: preview.export_token,
      idempotencyKey,
      passphrase,
    }),
  );
}

export async function loadProfileImportPreview(
  passphrase: string,
): Promise<ProfileImportPreview> {
  return assertSuccessful(
    await invoke<EngineResponse<ProfileImportPreview>>(
      "profile_import_preview",
      { passphrase },
    ),
  );
}

export async function stageProfileImport(
  preview: ProfileImportPreview,
  passphrase: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<{
  status: "staged_for_review";
  receipt_id: string;
  item_count: number;
  activates_artifacts: false;
}> {
  return assertSuccessful(
    await invoke<
      EngineResponse<{
        status: "staged_for_review";
        receipt_id: string;
        item_count: number;
        activates_artifacts: false;
      }>
    >("profile_import_stage", {
      expectedSnapshotDigest: snapshotDigest,
      idempotencyKey,
      importToken: preview.import_token,
      packageDigest: preview.package_digest,
      passphrase,
    }),
  );
}

export async function loadModes(): Promise<CapabilityModeSummary[]> {
  const result = assertSuccessful(
    await invoke<
      EngineResponse<{
        modes: CapabilityModeSummary[];
        raw_payloads_exposed: false;
      }>
    >("modes_list"),
  );
  if (result.raw_payloads_exposed) {
    throw new Error("Temper refused an unsafe Mode catalog.");
  }
  return result.modes;
}

export async function runModeTask(
  modeId: string,
  projectId: string,
  task: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineTaskResult> {
  return assertSuccessful(
    await invoke<EngineResponse<EngineTaskResult>>("mode_run_task", {
      expectedSnapshotDigest: snapshotDigest,
      idempotencyKey,
      modeId,
      projectId,
      task,
    }),
  );
}

export interface EngineTaskChangeReview {
  session_id: string;
  expected_head: string;
  changed_files: string[];
  diff_text: string;
  binary_change_count: number;
}

export interface EngineTaskResult {
  activation_id: string;
  status: string;
  projection_utf8_bytes: number;
  final_message: string | null;
  change_review: EngineTaskChangeReview | null;
  review_available: boolean;
  raw_payloads_exposed: false;
}

export interface EngineDiagnostics {
  diagnostics_version: "1.0.0";
  snapshot_version: string;
  project_count: number;
  pending_review_count: number;
  active_adaptation_count: number;
  pending_feedback_count: number;
  consent_current: boolean;
  secure_store_ready: boolean;
  raw_payloads_exposed: false;
}

export async function runManagedTask(
  projectId: string,
  task: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineTaskResult> {
  return assertSuccessful(
    await invoke<EngineResponse<EngineTaskResult>>("task_run", {
      expectedSnapshotDigest: snapshotDigest,
      idempotencyKey,
      projectId,
      task,
    }),
  );
}

export async function applyManagedTask(
  review: EngineTaskChangeReview,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("task_apply", {
    expectedHead: review.expected_head,
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
    sessionId: review.session_id,
  });
}

export async function discardManagedTask(
  sessionId: string,
  snapshotDigest: string,
  idempotencyKey: string,
): Promise<EngineMutationReceipt> {
  return invokeMutation("task_discard", {
    expectedSnapshotDigest: snapshotDigest,
    idempotencyKey,
    sessionId,
  });
}

export async function loadDiagnostics(): Promise<EngineDiagnostics> {
  const diagnostics = assertSuccessful(
    await invoke<EngineResponse<EngineDiagnostics>>("diagnostics_get"),
  );
  if (diagnostics.raw_payloads_exposed) {
    throw new Error("Temper refused unsafe diagnostics.");
  }
  return diagnostics;
}
