import { invoke } from "@tauri-apps/api/core";

import type { CapabilityModeSummary, PortableProfilePreview } from "./types";

export const ENGINE_PROTOCOL_VERSION = "temper-engine-protocol/v1" as const;

export interface EngineError {
  code: string;
  message: string;
  retryable: boolean;
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
}

export interface EngineProject {
  project_id: string;
  display_name: string;
  registered_prospectively: boolean;
  task_runner_enabled: boolean;
}

export interface EngineDesktopSnapshot {
  snapshot_version: "1.0.0";
  product_name: "Adaptation Compiler";
  health: "ready" | "needs_attention" | "paused" | "consent_expired";
  background_enabled: boolean;
  aggregate_reporting_enabled: boolean;
  projects: EngineProject[];
  generated_at: string;
  raw_payloads_exposed: false;
  terminal: {
    review_mode: {
      active_artifact_count: number;
      proposals: unknown[];
      activation_feedback: unknown[];
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
): Promise<{
  activation_id: string;
  status: string;
  projection_utf8_bytes: number;
  review_available: boolean;
}> {
  return assertSuccessful(
    await invoke<
      EngineResponse<{
        activation_id: string;
        status: string;
        projection_utf8_bytes: number;
        review_available: boolean;
      }>
    >("mode_run_task", {
      expectedSnapshotDigest: snapshotDigest,
      idempotencyKey,
      modeId,
      projectId,
      task,
    }),
  );
}
