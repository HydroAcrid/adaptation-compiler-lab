import { invoke } from "@tauri-apps/api/core";
import { ENGINE_PROTOCOL_VERSION, type EngineResponse } from "./engine";

export const setupKinds = {
  skill: "Skill",
  knowledge: "Knowledge",
  preference: "Preference",
  check: "Check",
} as const;

export type SetupKind = keyof typeof setupKinds;
export type SetupItem = {
  id: string;
  title: string;
} & (
  | { kind: Exclude<SetupKind, "check">; text: string }
  | {
      kind: "check";
      path: string;
      operation: "file_exists" | "file_contains";
      text?: string;
    }
);

export interface SetupPreview {
  title: string;
  items: SetupItem[];
  digest: string;
  signer_fingerprint: string;
}

export interface SetupImportPreview extends SetupPreview {
  project_id: string;
  source_name: string;
  active_digest: string | null;
}

export interface SetupStatus {
  active: SetupPreview | null;
  issue?: "unavailable";
  recovery_digest?: string | null;
}

async function request<T>(
  operation: string,
  args: Record<string, unknown>,
): Promise<T> {
  const response = await invoke<EngineResponse<T>>(
    `portable_setup_${operation}`,
    args,
  );
  if (response.protocol_version !== ENGINE_PROTOCOL_VERSION) {
    throw { code: "engine_incompatible" };
  }
  if (!response.ok || response.result === null) {
    throw response.error ?? { code: "engine_unavailable" };
  }
  return response.result;
}

export function previewSetupExport(title: string, items: SetupItem[]) {
  return request<SetupPreview>("export_preview", { title, items });
}

export function saveSetupFile(digest: string) {
  return request<SetupPreview>("export", {
    digest,
    idempotencyKey: crypto.randomUUID(),
  });
}

export function openSetupFile(projectId: string) {
  return request<SetupImportPreview>("import_preview", { projectId });
}

export function approveSetup(preview: SetupImportPreview) {
  return request<SetupPreview>("import_approve", {
    projectId: preview.project_id,
    digest: preview.digest,
    activeDigest: preview.active_digest,
    idempotencyKey: crypto.randomUUID(),
  });
}

export function loadSetupStatus(projectId: string) {
  return request<SetupStatus>("status", { projectId });
}

export function removeSetup(projectId: string, digest: string) {
  return request<SetupStatus>("remove", {
    projectId,
    digest,
    idempotencyKey: crypto.randomUUID(),
  });
}

export function resetSetup(projectId: string, digest: string) {
  return request<SetupStatus>("reset", {
    projectId,
    digest,
    idempotencyKey: crypto.randomUUID(),
  });
}
export interface SetupUpdateStatus {
  connected: boolean;
  available: boolean;
  can_rollback: boolean;
  issue?: string;
}

export interface SetupUpdatePreview extends SetupImportPreview {
  review_id: string;
  direction: "update" | "rollback";
  baseline_passed?: number;
  candidate_passed?: number;
  assertion_count?: number;
}

export function connectSetupUpdateSource(projectId: string) {
  return request<{ connected: true }>("update_source", {
    projectId,
    idempotencyKey: crypto.randomUUID(),
  });
}

export function loadSetupUpdateStatus(projectId: string) {
  return request<SetupUpdateStatus>("update_status", { projectId });
}

export function previewSetupUpdate(
  projectId: string,
  direction: SetupUpdatePreview["direction"],
) {
  return request<SetupUpdatePreview>(
    direction === "update" ? "update_preview" : "update_rollback_preview",
    { projectId },
  );
}

export function approveSetupUpdate(
  preview: SetupUpdatePreview,
  idempotencyKey: string,
) {
  return request<SetupPreview>("update_approve", {
    projectId: preview.project_id,
    reviewId: preview.review_id,
    idempotencyKey,
  });
}

export function disconnectSetupUpdateSource(projectId: string) {
  return request<{ connected: false }>("update_disconnect", {
    projectId,
    idempotencyKey: crypto.randomUUID(),
  });
}
