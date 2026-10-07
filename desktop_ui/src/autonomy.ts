import { invoke } from "@tauri-apps/api/core";
import type { EngineResponse } from "./engine";

export type StyleCategory =
  "communication_detail" | "presentation_style" | "suggestion_style";
export interface Habit {
  habit_id: string;
  behavior: string;
  project_id: string;
  task_class: string;
  origin: "inferred" | "expressed_preference";
  state: "provisional" | "trial" | "active" | "paused" | "retired";
  support_episode_ids: string[];
  contradiction_episode_ids: string[];
}
export interface AutonomyState {
  grant_enabled: boolean;
  learning_enabled: boolean;
  personalization_enabled: boolean;
  automatic_serving_ready: boolean;
  secure_store_ready: boolean;
  provenance_state: "verified" | "unverified";
  capture_state: string;
  mode: "shadow" | "automatic";
  published: boolean;
  delivery_confirmed: boolean;
  publication_needs_attention: boolean;
  habits: Habit[];
  recent_changes: { type: string; digest: string }[];
  raw_payloads_exposed: false;
}
export interface GrantPreview {
  preview_token: string;
  native_destination: string;
  project_ids: string[];
  categories: StyleCategory[];
  permission_duration: "until_disabled";
  raw_retention_days: 30;
  effect: string;
  raw_payloads_exposed: false;
}
export type AutonomyControl =
  | "pause_learning"
  | "resume_learning"
  | "enable_personalization"
  | "disable_personalization"
  | "revoke_grant"
  | "revoke_habit";
export interface Bound<T> {
  value: T;
  digest: string;
}

async function request<T extends { raw_payloads_exposed: false }>(
  command: string,
  args?: Record<string, unknown>,
): Promise<Bound<T>> {
  const response = await invoke<EngineResponse<T>>(command, args);
  if (!response.ok || !response.result || !response.snapshot_digest) {
    throw new Error(
      response.error?.message ?? "Temper learning status is unavailable.",
    );
  }
  if (response.result.raw_payloads_exposed !== false) {
    throw new Error("Temper refused unsafe learning details.");
  }
  return { value: response.result, digest: response.snapshot_digest };
}

export function loadAutonomy(): Promise<Bound<AutonomyState>> {
  return request("autonomy_status");
}
export function previewLearningGrant(
  projectIds: string[],
  categories: StyleCategory[],
): Promise<Bound<GrantPreview>> {
  return request("autonomy_grant_preview", { projectIds, categories });
}
export function enableLearningGrant(
  preview: Bound<GrantPreview>,
): Promise<Bound<AutonomyState>> {
  return request("autonomy_grant_enable", {
    previewToken: preview.value.preview_token,
    confirmed: true,
    expectedSnapshotDigest: preview.digest,
    idempotencyKey: crypto.randomUUID(),
  });
}
export function controlAutonomy(
  action: AutonomyControl,
  digest: string,
  habitId?: string,
): Promise<Bound<AutonomyState>> {
  return request("autonomy_control", {
    action,
    habitId: habitId ?? null,
    expectedSnapshotDigest: digest,
    idempotencyKey: crypto.randomUUID(),
  });
}
export function explainHabit(habitId: string): Promise<
  Bound<{
    habit: Habit;
    support_count: number;
    contradiction_count: number;
    raw_payloads_exposed: false;
  }>
> {
  return request("autonomy_habit_explain", { habitId });
}
export function previewHabitApplicability(
  projectId: string,
  taskClass: string,
): Promise<
  Bound<{ applies: string[]; excluded: string[]; raw_payloads_exposed: false }>
> {
  return request("autonomy_applicability_preview", { projectId, taskClass });
}
