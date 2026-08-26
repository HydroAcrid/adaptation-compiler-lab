import { beforeEach, describe, expect, it, vi } from "vitest";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import {
  ENGINE_PROTOCOL_VERSION,
  exportProfile,
  isTauriRuntime,
  loadEngineSnapshot,
  loadModes,
  loadProfileImportPreview,
  runModeTask,
} from "./engine";

describe("Tauri engine boundary", () => {
  beforeEach(() => {
    invoke.mockReset();
    delete window.__TAURI_INTERNALS__;
  });

  it("does not mistake the browser prototype for a native runtime", () => {
    expect(isTauriRuntime()).toBe(false);
    window.__TAURI_INTERNALS__ = {};
    expect(isTauriRuntime()).toBe(true);
  });

  it("handshakes before loading a raw-free snapshot", async () => {
    invoke
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "one",
        ok: true,
        result: {
          protocol_version: ENGINE_PROTOCOL_VERSION,
          engine_version: "0.3.0a1",
          snapshot_schema_digest: "sha256:" + "a".repeat(64),
          mutation_enabled: false,
          configured: true,
        },
        error: null,
        snapshot_digest: null,
      })
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "two",
        ok: true,
        result: {
          snapshot_version: "1.0.0",
          product_name: "Temper",
          health: "ready",
          background_enabled: true,
          aggregate_reporting_enabled: false,
          projects: [],
          generated_at: "2026-08-24T00:00:00Z",
          raw_payloads_exposed: false,
          terminal: {
            review_mode: {
              active_artifact_count: 0,
              proposals: [],
              activation_feedback: [],
              metrics: { pending_review_count: 0, pending_feedback_count: 0 },
            },
            active_adaptations: [],
            latest_delivered_projection_utf8_bytes: 0,
            raw_payloads_exposed: false,
          },
        },
        error: null,
        snapshot_digest: "sha256:" + "b".repeat(64),
      });

    const result = await loadEngineSnapshot();

    expect(result.snapshot.health).toBe("ready");
    expect(invoke.mock.calls.map(([method]) => method)).toEqual([
      "engine_handshake",
      "snapshot_get",
    ]);
  });

  it("fails closed on a protocol mismatch", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: "temper-engine-protocol/v2",
      request_id: "one",
      ok: true,
      result: {},
      error: null,
      snapshot_digest: null,
    });

    await expect(loadEngineSnapshot()).rejects.toThrow("versions do not match");
    expect(invoke).toHaveBeenCalledTimes(1);
  });

  it("rejects snapshots that claim to expose raw payloads", async () => {
    invoke
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "one",
        ok: true,
        result: {
          protocol_version: ENGINE_PROTOCOL_VERSION,
          engine_version: "0.3.0a1",
          snapshot_schema_digest: "sha256:" + "a".repeat(64),
          mutation_enabled: false,
          configured: true,
        },
        error: null,
        snapshot_digest: null,
      })
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "two",
        ok: true,
        result: {
          raw_payloads_exposed: true,
          terminal: { raw_payloads_exposed: false },
        },
        error: null,
        snapshot_digest: "sha256:" + "b".repeat(64),
      });

    await expect(loadEngineSnapshot()).rejects.toThrow(
      "unsafe desktop snapshot",
    );
  });

  it("keeps native profile paths out of renderer arguments", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "one",
      ok: true,
      result: {
        status: "exported",
        package_digest: "sha256:" + "a".repeat(64),
        item_count: 2,
      },
      error: null,
      snapshot_digest: "sha256:" + "b".repeat(64),
    });

    await exportProfile(
      {
        activates_nothing: true,
        display_name: "Temper Core",
        export_token: "opaque-token",
        item_count: 2,
        items: [],
        package_digest: "sha256:" + "a".repeat(64),
        package_id: "temper-core",
        raw_payloads_exposed: false,
        scope_mapping_count: 0,
        source_key_fingerprint: "sha256:" + "c".repeat(64),
        source_signature_verified: true,
        warnings: [],
      },
      "correct horse battery staple",
      "sha256:" + "b".repeat(64),
      "one-click",
    );

    expect(invoke).toHaveBeenCalledWith("profile_export", {
      expectedSnapshotDigest: "sha256:" + "b".repeat(64),
      exportToken: "opaque-token",
      idempotencyKey: "one-click",
      passphrase: "correct horse battery staple",
    });
    expect(JSON.stringify(invoke.mock.calls[0])).not.toContain("Users");
  });

  it("delegates import file choice to the native command", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "one",
      ok: true,
      result: { import_token: "opaque", raw_payloads_exposed: false },
      error: null,
      snapshot_digest: null,
    });

    await loadProfileImportPreview("correct horse battery staple");

    expect(invoke).toHaveBeenCalledWith("profile_import_preview", {
      passphrase: "correct horse battery staple",
    });
  });

  it("loads only the raw-free Mode catalog", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "one",
      ok: true,
      result: {
        modes: [{ mode_id: "frontend-studio" }],
        raw_payloads_exposed: false,
      },
      error: null,
      snapshot_digest: null,
    });

    const modes = await loadModes();

    expect(modes[0]?.mode_id).toBe("frontend-studio");
    expect(invoke).toHaveBeenCalledWith("modes_list");
  });

  it("binds a Mode run to one exact project, task, snapshot, and retry key", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "one",
      ok: true,
      result: {
        activation_id: "mode-run-1",
        status: "review_available",
        projection_utf8_bytes: 1200,
        review_available: true,
      },
      error: null,
      snapshot_digest: "sha256:" + "c".repeat(64),
    });

    await runModeTask(
      "frontend-studio",
      "kairn",
      "Refine the settings page",
      "sha256:" + "b".repeat(64),
      "mode-click-1",
    );

    expect(invoke).toHaveBeenCalledWith("mode_run_task", {
      expectedSnapshotDigest: "sha256:" + "b".repeat(64),
      idempotencyKey: "mode-click-1",
      modeId: "frontend-studio",
      projectId: "kairn",
      task: "Refine the settings page",
    });
  });
});
