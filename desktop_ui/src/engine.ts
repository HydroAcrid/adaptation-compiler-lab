import { invoke } from "@tauri-apps/api/core";

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
    active_adaptations: unknown[];
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
  return { handshake, snapshot };
}
