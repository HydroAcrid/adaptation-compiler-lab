import { beforeEach, describe, expect, it, vi } from "vitest";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import {
  ENGINE_PROTOCOL_VERSION,
  isTauriRuntime,
  loadEngineSnapshot,
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
          engine_version: "0.2.0a1",
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
          product_name: "Adaptation Compiler",
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
          engine_version: "0.2.0a1",
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
});
