import { invoke } from "@tauri-apps/api/core";
import { ENGINE_PROTOCOL_VERSION, type EngineResponse } from "./engine";

export interface HubProject {
  id: string;
  label: string;
  root: string;
  paused: boolean;
  active: string[];
  pending_recovery: boolean;
  attention?: { status: string; conflicts: string[] } | null;
  can_rollback?: boolean;
}
export interface HubState {
  version: 1;
  digest: string;
  enabled: boolean;
  paused: boolean;
  project_count: number;
  projects: HubProject[];
  sources: { id: string; label: string; url: string; approved: boolean }[];
  manager: string;
  manager_ready: boolean;
  indexed: boolean;
  bridge_configured: boolean;
  cleanup_pending: boolean;
  secure_store_ready?: boolean;
  last_checked: number | null;
  last_task?: {
    state: string;
    project_id: string;
    status?: string;
    message?: string;
  } | null;
  job: null | {
    job_id: string;
    operation: string;
    state: "running" | "complete" | "failed" | "interrupted";
    message?: string;
    result?: {
      status?: string;
      skills?: number;
      projects?: { project_id: string; status: string; conflicts?: string[] }[];
    };
  };
}
export interface HubPreview {
  preview_id: string;
  destinations: string[];
  manager_destination: string;
  projects: { id: string; root: string }[];
  source_specs: { id: string; url: string; ref: string; roots: string[] }[];
}
export interface ConnectionPreview {
  preview_id: string;
  files: { path: string; block: string }[];
  new_chat_required: true;
}
export type HubOperation =
  | "status"
  | "inventory"
  | "permission_preview"
  | "permission_enable"
  | "control"
  | "connection_preview"
  | "connection_apply"
  | "refresh"
  | "repair";

export async function hubRequest<T>(
  operation: HubOperation,
  params: object = {},
  digest?: string,
): Promise<T> {
  const response = await invoke<EngineResponse<T>>("tools_hub_request", {
    operation,
    params,
    expectedDigest: digest ?? null,
    idempotencyKey: digest ? crypto.randomUUID() : null,
  });
  if (
    response.protocol_version !== ENGINE_PROTOCOL_VERSION ||
    !response.ok ||
    !response.result
  ) {
    throw new Error(
      response.error?.message ??
        "Repository setup is unavailable. Try refreshing its status.",
    );
  }
  return response.result;
}
