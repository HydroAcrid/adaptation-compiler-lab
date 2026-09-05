import { beforeEach, describe, expect, it, vi } from "vitest";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import {
  adoptExistingInstallation,
  applyNativeInstructionChange,
  ENGINE_PROTOCOL_VERSION,
  exportPackage,
  exportProfile,
  decideEngineSuggestion,
  isTauriRuntime,
  loadEngineSnapshot,
  loadInstructionEnvironments,
  loadDiagnostics,
  loadModes,
  loadPackageImportPreview,
  loadProfileImportPreview,
  previewExistingInstallation,
  previewNativeInstructionChange,
  previewPersonalInstructionSetup,
  previewSetupProject,
  requestNotificationPermission,
  runModeTask,
  runManagedTask,
  stagePackageImport,
  applyManagedTask,
  discardManagedTask,
  updateEnginePreferences,
  enablePersonalInstructionSetup,
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

  it("requests notification permission through one allowlisted native command", async () => {
    invoke.mockResolvedValueOnce("granted");

    await expect(requestNotificationPermission()).resolves.toBe("granted");
    expect(invoke).toHaveBeenCalledWith("notification_permission", {
      request: true,
    });
  });

  it("handshakes before loading a raw-free snapshot", async () => {
    invoke
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "one",
        ok: true,
        result: {
          protocol_version: ENGINE_PROTOCOL_VERSION,
          engine_version: "0.3.0a2",
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
          snapshot_version: "1.1.0",
          product_name: "Temper",
          health: "ready",
          background_enabled: true,
          aggregate_reporting_enabled: false,
          projects: [],
          consent: {
            effective_at: "2026-08-24T00:00:00Z",
            expires_at: "2026-09-23T00:00:00Z",
            retention_days: 30,
            days_remaining: 27,
            renewal_required: false,
          },
          suggestions: [],
          adaptations: [],
          activation_feedback: [],
          recent_undos: [],
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
          engine_version: "0.3.0a2",
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

  it("keeps shareable package paths in native dialogs and stages nothing active", async () => {
    const preview = {
      import_token: "opaque-package-token",
      package_type: "capability_mode" as const,
      package_id: "frontend-studio-package",
      release_version: "1.0.0",
      package_digest: "sha256:" + "a".repeat(64),
      display_name: "Frontend Studio",
      publisher_name: "Temper",
      publisher_key_fingerprint: "sha256:" + "c".repeat(64),
      source_license: "Apache-2.0",
      origin_signature_verified: true as const,
      item_count: 1,
      items: [],
      duplicate_item_ids: [],
      conflicting_item_ids: [],
      requested_scope_mapping_count: 0,
      required_capabilities: [],
      evaluation_status: "experimental",
      warnings: [],
      starts_inactive: true as const,
      grants_user_authority: false as const,
      raw_payloads_exposed: false as const,
    };
    invoke
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "preview",
        ok: true,
        result: preview,
        error: null,
        snapshot_digest: null,
      })
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "stage",
        ok: true,
        result: {
          status: "staged_inactive_for_review",
          receipt_id: "receipt-1",
          item_count: 1,
          activates_artifacts: false,
          raw_payloads_exposed: false,
        },
        error: null,
        snapshot_digest: "sha256:" + "b".repeat(64),
      });

    await expect(loadPackageImportPreview()).resolves.toEqual(preview);
    await stagePackageImport(
      preview,
      "sha256:" + "b".repeat(64),
      "package-import-click",
    );

    expect(invoke.mock.calls).toEqual([
      ["package_import_preview"],
      [
        "package_import_stage",
        {
          expectedSnapshotDigest: "sha256:" + "b".repeat(64),
          idempotencyKey: "package-import-click",
          importToken: "opaque-package-token",
          packageDigest: "sha256:" + "a".repeat(64),
        },
      ],
    ]);
    expect(JSON.stringify(invoke.mock.calls)).not.toContain("Users");
  });

  it("exports a shareable package through a native-owned destination", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "export",
      ok: true,
      result: {
        status: "exported",
        package_digest: "sha256:" + "a".repeat(64),
        file_name: "frontend-studio-package.temper-pack",
        raw_payloads_exposed: false,
      },
      error: null,
      snapshot_digest: "sha256:" + "b".repeat(64),
    });

    await exportPackage(
      {
        export_token: "opaque-export",
        package_type: "capability_mode",
        package_id: "frontend-studio-package",
        release_version: "1.0.0",
        package_digest: "sha256:" + "a".repeat(64),
        display_name: "Frontend Studio",
        publisher_name: "Temper",
        publisher_key_fingerprint: "sha256:" + "c".repeat(64),
        source_license: "Apache-2.0",
        origin_signature_verified: true,
        item_count: 1,
        items: [],
        duplicate_item_ids: [],
        conflicting_item_ids: [],
        requested_scope_mapping_count: 0,
        required_capabilities: [],
        evaluation_status: "experimental",
        warnings: [],
        starts_inactive: true,
        grants_user_authority: false,
        raw_payloads_exposed: false,
      },
      "frontend-studio-package.temper-pack",
      "sha256:" + "b".repeat(64),
      "package-export-click",
    );

    expect(invoke).toHaveBeenCalledWith("package_export", {
      expectedSnapshotDigest: "sha256:" + "b".repeat(64),
      exportToken: "opaque-export",
      idempotencyKey: "package-export-click",
      suggestedName: "frontend-studio-package.temper-pack",
    });
  });

  it("adopts an existing identity through an opaque digest-bound preview", async () => {
    const installation = {
      signer_fingerprint: "sha256:" + "c".repeat(64),
      project_count: 2,
      consent_expires_at: "2026-09-20T00:00:00Z",
      secure_store_ready: true,
    };
    invoke
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "preview",
        ok: true,
        result: {
          preview_token: "opaque-installation",
          installation,
          raw_payloads_exposed: false,
        },
        error: null,
        snapshot_digest: null,
      })
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "adopt",
        ok: true,
        result: { installation, restart_required: true },
        error: null,
        snapshot_digest: null,
      });

    const preview = await previewExistingInstallation();
    expect(preview).not.toBeNull();
    await adoptExistingInstallation(
      preview!.preview_token,
      "sha256:" + "b".repeat(64),
      "adopt-click-1",
    );

    expect(invoke.mock.calls).toEqual([
      ["setup_existing_preview"],
      [
        "setup_existing_adopt",
        {
          expectedSnapshotDigest: "sha256:" + "b".repeat(64),
          idempotencyKey: "adopt-click-1",
          previewToken: "opaque-installation",
        },
      ],
    ]);
    expect(JSON.stringify(invoke.mock.calls)).not.toContain("config.json");
  });

  it("treats a cancelled native picker as an unchanged state", async () => {
    const cancelled = {
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "cancelled",
      ok: false,
      result: null,
      error: {
        code: "cancelled",
        message: "Nothing changed.",
        retryable: false,
      },
      snapshot_digest: null,
    };
    invoke.mockResolvedValue(cancelled);

    await expect(previewSetupProject()).resolves.toBeNull();
    await expect(previewExistingInstallation()).resolves.toBeNull();
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

  it("binds a governed review decision without sending evidence or paths", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "one",
      ok: true,
      result: {
        receipt_version: "1.0.0",
        action: "approve",
        target_id: "review-1",
        status: "applied",
        code: "ok",
        message: "Saved.",
        resulting_snapshot_digest: "sha256:" + "c".repeat(64),
        raw_payloads_exposed: false,
      },
      error: null,
      snapshot_digest: "sha256:" + "c".repeat(64),
    });

    await decideEngineSuggestion(
      {
        summary_version: "1.0.0",
        review_number: 1,
        queue_id: "review-1",
        proposal_digest: "sha256:" + "a".repeat(64),
        signal_kind: "preference",
        proposed_behavior: "Explain purpose first.",
        affected_artifact_id: null,
        route: "preference",
        layer: "permanent_profile",
        suggested_scope: {
          subject_ids: ["kevin"],
          workspace_ids: [],
          project_ids: [],
          repository_ids: [],
          task_classes: [],
          target_families: [],
          environment_ids: [],
          activation_conditions: [],
          exclusions: [],
          valid_from: null,
          valid_until: null,
        },
        reason_summary: ["Direct user preference."],
        evidence_digest: "sha256:" + "d".repeat(64),
        consent_digest: "sha256:" + "e".repeat(64),
        capture_digest: "sha256:" + "f".repeat(64),
        available_actions: [
          "keep_suggested",
          "keep_project",
          "keep_narrowed",
          "ignore",
        ],
        created_at: "2026-08-27T00:00:00Z",
        raw_payloads_exposed: false,
      },
      "keep_suggested",
      "sha256:" + "b".repeat(64),
      "review-click-1",
    );

    expect(invoke).toHaveBeenCalledWith("review_decide", {
      decision: "keep_suggested",
      expectedSnapshotDigest: "sha256:" + "b".repeat(64),
      idempotencyKey: "review-click-1",
      projectId: null,
      proposalDigest: "sha256:" + "a".repeat(64),
      queueId: "review-1",
      refinedScope: null,
    });
    expect(JSON.stringify(invoke.mock.calls)).not.toContain("evidence_digest");
  });

  it("persists only the four allowlisted local product preferences", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "one",
      ok: true,
      result: {
        receipt_version: "1.0.0",
        action: "preferences",
        target_id: "local-preferences",
        status: "applied",
        code: "ok",
        message: "Saved.",
        resulting_snapshot_digest: "sha256:" + "c".repeat(64),
        raw_payloads_exposed: false,
      },
      error: null,
      snapshot_digest: "sha256:" + "c".repeat(64),
    });

    await updateEnginePreferences(
      true,
      false,
      true,
      false,
      "sha256:" + "b".repeat(64),
      "preferences-click-1",
    );

    expect(invoke).toHaveBeenCalledWith("preferences_update", {
      expectedSnapshotDigest: "sha256:" + "b".repeat(64),
      idempotencyKey: "preferences-click-1",
      preferences: {
        aggregateReportingEnabled: false,
        backgroundEnabled: true,
        decisionNotificationsEnabled: true,
        launchAtLoginEnabled: false,
      },
    });
  });

  it("binds managed task run, apply, and discard to one exact review", async () => {
    const review = {
      session_id: "session-1",
      expected_head: "0123456789abcdef",
      changed_files: ["src/example.py"],
      diff_text: "diff --git a/src/example.py b/src/example.py",
      binary_change_count: 0,
    };
    invoke
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "run",
        ok: true,
        result: {
          activation_id: "activation-1",
          status: "review_available",
          projection_utf8_bytes: 400,
          final_message: "Prepared a change.",
          change_review: review,
          review_available: true,
          raw_payloads_exposed: false,
        },
        error: null,
        snapshot_digest: "sha256:" + "c".repeat(64),
      })
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "apply",
        ok: true,
        result: {
          receipt_version: "1.0.0",
          action: "apply_changes",
          target_id: "session-1",
          status: "applied",
          code: "ok",
          message: "Applied.",
          resulting_snapshot_digest: "sha256:" + "c".repeat(64),
          raw_payloads_exposed: false,
        },
        error: null,
        snapshot_digest: "sha256:" + "c".repeat(64),
      })
      .mockResolvedValueOnce({
        protocol_version: ENGINE_PROTOCOL_VERSION,
        request_id: "discard",
        ok: true,
        result: {
          receipt_version: "1.0.0",
          action: "discard_changes",
          target_id: "session-1",
          status: "applied",
          code: "ok",
          message: "Discarded.",
          resulting_snapshot_digest: "sha256:" + "c".repeat(64),
          raw_payloads_exposed: false,
        },
        error: null,
        snapshot_digest: "sha256:" + "c".repeat(64),
      });

    await runManagedTask(
      "kairn",
      "Fix the verified issue.",
      "sha256:" + "b".repeat(64),
      "run-click-1",
    );
    await applyManagedTask(review, "sha256:" + "c".repeat(64), "apply-click-1");
    await discardManagedTask(
      "session-1",
      "sha256:" + "c".repeat(64),
      "discard-click-1",
    );

    expect(invoke.mock.calls).toEqual([
      [
        "task_run",
        {
          expectedSnapshotDigest: "sha256:" + "b".repeat(64),
          idempotencyKey: "run-click-1",
          projectId: "kairn",
          task: "Fix the verified issue.",
        },
      ],
      [
        "task_apply",
        {
          expectedHead: "0123456789abcdef",
          expectedSnapshotDigest: "sha256:" + "c".repeat(64),
          idempotencyKey: "apply-click-1",
          sessionId: "session-1",
        },
      ],
      [
        "task_discard",
        {
          expectedSnapshotDigest: "sha256:" + "c".repeat(64),
          idempotencyKey: "discard-click-1",
          sessionId: "session-1",
        },
      ],
    ]);
  });

  it("rejects diagnostics that claim to expose raw content", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "diagnostics",
      ok: true,
      result: {
        diagnostics_version: "1.0.0",
        snapshot_version: "1.1.0",
        project_count: 2,
        pending_review_count: 1,
        active_adaptation_count: 3,
        pending_feedback_count: 0,
        consent_current: true,
        secure_store_ready: true,
        raw_payloads_exposed: true,
      },
      error: null,
      snapshot_digest: "sha256:" + "c".repeat(64),
    });

    await expect(loadDiagnostics()).rejects.toThrow("unsafe diagnostics");
  });

  it("loads only raw-free observed instruction-environment summaries", async () => {
    invoke.mockResolvedValueOnce({
      protocol_version: ENGINE_PROTOCOL_VERSION,
      request_id: "instructions",
      ok: true,
      result: {
        environments: [
          {
            summary_version: "1.0.0",
            project_id: "project-alpha",
            target: "codex",
            status: "understood",
            source_count: 1,
            skill_count: 0,
            instruction_count: 2,
            blocking_conflict_count: 0,
            semantic_analysis_status: "current",
            last_analyzed_at: "2026-08-28T12:00:00Z",
            environment_digest: "sha256:" + "a".repeat(64),
            source_chain_digest: "sha256:" + "b".repeat(64),
            global_sources_enabled: false,
            sources: [
              {
                summary_version: "1.0.0",
                source_id: "native-source-1",
                target: "codex",
                kind: "project_instructions",
                display_path: "AGENTS.md",
                scope_summary: "Project project-alpha",
                status: "ready",
                instruction_count: 2,
                skill: false,
                activation_status: "active",
                observed_context_only: true,
                raw_payloads_exposed: false,
              },
            ],
            raw_payloads_exposed: false,
          },
        ],
        raw_payloads_exposed: false,
      },
      error: null,
      snapshot_digest: null,
    });

    await expect(loadInstructionEnvironments()).resolves.toHaveLength(1);
    expect(invoke).toHaveBeenCalledWith("instruction_environment_get");
    expect(JSON.stringify(invoke.mock.calls)).not.toMatch(/[A-Z]:\\|\/Users\//);
  });

  it("keeps personal inspection path selection native and enables only an opaque preview", async () => {
    const preview = {
      preview_version: "1.0.0" as const,
      preview_token: "personal-preview-1",
      target: "codex" as const,
      categories: ["instructions", "skills"],
      source_count: 2,
      skill_count: 1,
      modifies_files: false as const,
      authorizes_learning: false as const,
      expires_at: "2026-08-28T12:15:00Z",
      raw_payloads_exposed: false as const,
    };
    invoke
      .mockResolvedValueOnce(responseForTest(preview))
      .mockResolvedValueOnce(
        responseForTest({ environments: [], raw_payloads_exposed: false }),
      );

    await expect(previewPersonalInstructionSetup("codex")).resolves.toEqual(
      preview,
    );
    await enablePersonalInstructionSetup(
      preview.preview_token,
      preview.target,
      "sha256:" + "c".repeat(64),
      "enable-personal-1",
    );

    expect(invoke.mock.calls).toEqual([
      ["instruction_environment_global_preview", { target: "codex" }],
      [
        "instruction_environment_global_enable",
        {
          expectedSnapshotDigest: "sha256:" + "c".repeat(64),
          idempotencyKey: "enable-personal-1",
          previewToken: "personal-preview-1",
          target: "codex",
        },
      ],
    ]);
  });

  it("binds native writeback to the exact source and environment preview", async () => {
    const environment = {
      summary_version: "1.0.0" as const,
      project_id: "project-alpha",
      target: "codex" as const,
      status: "understood" as const,
      source_count: 1,
      skill_count: 0,
      instruction_count: 1,
      blocking_conflict_count: 0,
      semantic_analysis_status: "current" as const,
      last_analyzed_at: "2026-08-28T12:00:00Z",
      environment_digest: "sha256:" + "a".repeat(64),
      source_chain_digest: "sha256:" + "b".repeat(64),
      global_sources_enabled: false,
      sources: [],
      raw_payloads_exposed: false as const,
    };
    const preview = {
      preview_version: "1.0.0" as const,
      preview_token: "write-preview-1",
      project_id: "project-alpha",
      target: "codex" as const,
      source_id: "native-source-1",
      source_digest: "sha256:" + "d".repeat(64),
      expected_environment_digest: environment.environment_digest,
      operation: "update_temper_section" as const,
      display_path: "AGENTS.md",
      unified_diff: "--- a/AGENTS.md\n+++ b/AGENTS.md\n",
      resulting_digest: "sha256:" + "e".repeat(64),
      expires_at: "2026-08-28T12:15:00Z",
      raw_payloads_exposed: false as const,
    };
    invoke
      .mockResolvedValueOnce(responseForTest(preview))
      .mockResolvedValueOnce(
        responseForTest({
          receipt_version: "1.0.0",
          receipt_id: "native-receipt-1",
          preview_token: preview.preview_token,
          project_id: "project-alpha",
          target: "codex",
          source_id: "native-source-1",
          before_digest: preview.source_digest,
          after_digest: preview.resulting_digest,
          environment_digest_before: environment.environment_digest,
          environment_digest_after: "sha256:" + "f".repeat(64),
          backup_digest: "sha256:" + "1".repeat(64),
          applied_at: "2026-08-28T12:01:00Z",
          signer_fingerprint: "sha256:" + "2".repeat(64),
          signature_base64: "signed",
          rollback_available_until: "2026-09-27T12:01:00Z",
          status: "applied",
          raw_payloads_exposed: false,
        }),
      );

    const result = await previewNativeInstructionChange(
      environment,
      "native-source-1",
      "Verify the focused test.",
      "sha256:" + "c".repeat(64),
    );
    await applyNativeInstructionChange(
      result,
      "sha256:" + "c".repeat(64),
      "apply-native-1",
    );

    expect(invoke.mock.calls[0]).toEqual([
      "instruction_environment_change_preview",
      {
        expectedEnvironmentDigest: environment.environment_digest,
        expectedSnapshotDigest: "sha256:" + "c".repeat(64),
        instructionText: "Verify the focused test.",
        projectId: "project-alpha",
        sourceId: "native-source-1",
        target: "codex",
      },
    ]);
    expect(invoke.mock.calls[1]?.[1]).toEqual({
      expectedEnvironmentDigest: environment.environment_digest,
      expectedSnapshotDigest: "sha256:" + "c".repeat(64),
      idempotencyKey: "apply-native-1",
      previewToken: "write-preview-1",
      target: "codex",
    });
  });
});

function responseForTest(result: unknown) {
  return {
    protocol_version: ENGINE_PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    ok: true,
    result,
    error: null,
    snapshot_digest: null,
  };
}
