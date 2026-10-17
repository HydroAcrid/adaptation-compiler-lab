import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import App from "./App";
import { ENGINE_PROTOCOL_VERSION } from "./engine";

const digest = `sha256:${"a".repeat(64)}`;

function response(result: unknown, snapshotDigest: string | null = null) {
  return {
    protocol_version: ENGINE_PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    ok: true,
    result,
    error: null,
    snapshot_digest: snapshotDigest,
  };
}

function handshake(configured: boolean) {
  return response({
    protocol_version: ENGINE_PROTOCOL_VERSION,
    engine_version: "0.3.0a2",
    snapshot_schema_digest: digest,
    mutation_enabled: configured,
    configured,
    setup_available: true,
    configuration_state: configured ? "configured" : "unconfigured",
    platform: "windows",
    architecture: "x86_64",
  });
}

const setup = {
  setup_version: "1.0.0",
  product_name: "Temper",
  configuration_state: "unconfigured",
  secure_store: {
    platform: "windows",
    protector: "windows-dpapi-current-user",
    status: "not_created",
  },
  connections: [
    {
      connection_version: "1.1.0",
      integration_state: "unavailable",
      agent_id: "codex",
      display_name: "Codex",
      installation_state: "not_installed",
      authentication_state: "unknown",
      conformance_state: "unverified",
      version_label: null,
      status_summary: "Codex was not found.",
      learning_capability: "Unavailable",
      delivery_capability: "Unavailable",
      cost_posture: "No provider call during setup",
      available_actions: ["refresh"],
      raw_payloads_exposed: false,
    },
    {
      connection_version: "1.1.0",
      integration_state: "unavailable",
      agent_id: "claude",
      display_name: "Claude Code",
      installation_state: "not_installed",
      authentication_state: "unknown",
      conformance_state: "not_applicable",
      version_label: null,
      status_summary: "Claude Code was not found.",
      learning_capability: "Unavailable",
      delivery_capability: "Unavailable",
      cost_posture: "Provider-billed use is not enabled",
      available_actions: ["refresh"],
      raw_payloads_exposed: false,
    },
  ],
  existing_installation: null,
  learning_enabled: false,
  automatic_promotion_enabled: false,
  aggregate_reporting_enabled: false,
  launch_at_login_enabled: false,
  raw_payloads_exposed: false,
};

const snapshot = {
  snapshot_version: "1.1.0",
  product_name: "Temper",
  health: "ready",
  background_enabled: true,
  aggregate_reporting_enabled: false,
  decision_notifications_enabled: false,
  launch_at_login_enabled: false,
  projects: [
    {
      project_id: "project-alpha",
      display_name: "Alpha",
      registered_prospectively: true,
      task_runner_enabled: true,
    },
    {
      project_id: "project-beta",
      display_name: "Beta",
      registered_prospectively: true,
      task_runner_enabled: true,
    },
  ],
  generated_at: "2026-08-27T12:00:00Z",
  raw_payloads_exposed: false,
  consent: {
    effective_at: "2026-08-27T12:00:00Z",
    expires_at: "2026-09-26T12:00:00Z",
    retention_days: 30,
    days_remaining: 30,
    renewal_required: false,
  },
  suggestions: [],
  adaptations: [],
  activation_feedback: [],
  recent_undos: [],
  terminal: {
    review_mode: {
      active_artifact_count: 0,
      proposals: [],
      activation_feedback: [],
      metrics: { pending_review_count: 0, pending_feedback_count: 0 },
      gate: {
        goal_interaction_count: 20,
        minimum_active_dates: 3,
        minimum_activation_count: 6,
        eligible_interaction_count: 13,
        active_date_count: 4,
        assessed_interaction_count: 13,
        correct_learning_count: 11,
        false_learning_count: 1,
        missed_learning_count: 1,
        activation_count: 2,
        completed_activation_count: 2,
        rated_activation_count: 2,
        helped_count: 1,
        hurt_count: 0,
        irrelevant_count: 1,
        correct_activation_count: 1,
        false_activation_count: 1,
        missed_activation_count: 0,
        repeated_correction_count: 0,
        pack_bytes_by_activation: [512, 634],
        remaining_interactions: 7,
        evidence_ready: false,
      },
    },
    active_adaptations: [],
    latest_delivered_projection_utf8_bytes: 0,
    raw_payloads_exposed: false,
  },
};

const configuredSetup = {
  ...setup,
  configuration_state: "configured",
  secure_store: { ...setup.secure_store, status: "ready" },
};

const emptyScope = {
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
};

const globalSuggestion = {
  summary_version: "1.0.0",
  review_number: 1,
  queue_id: "review-global",
  proposal_digest: digest,
  signal_kind: "preference",
  proposed_behavior: "Explain the purpose before setup steps.",
  affected_artifact_id: null,
  route: "preference",
  layer: "permanent_profile",
  suggested_scope: emptyScope,
  reason_summary: ["Direct approved feedback."],
  evidence_digest: digest,
  consent_digest: digest,
  capture_digest: digest,
  available_actions: [
    "keep_suggested",
    "keep_project",
    "keep_narrowed",
    "ignore",
  ],
  created_at: "2026-08-27T12:00:00Z",
  raw_payloads_exposed: false,
};

const twoProjectSuggestion = {
  ...globalSuggestion,
  review_number: 2,
  queue_id: "review-two-projects",
  proposed_behavior: "Confirm recovery risks before synchronizing work.",
  suggested_scope: {
    ...emptyScope,
    project_ids: ["project-alpha", "project-beta"],
  },
  available_actions: ["keep_suggested", "keep_narrowed", "ignore"],
};

const betaSuggestion = {
  ...twoProjectSuggestion,
  queue_id: "review-beta",
  suggested_scope: {
    ...emptyScope,
    project_ids: ["project-beta"],
  },
  available_actions: ["keep_suggested", "ignore"],
};

afterEach(() => {
  cleanup();
  invoke.mockReset();
  delete window.__TAURI_INTERNALS__;
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("installed Temper state boundaries", () => {
  it("shows a single recovery state when the local engine fails", async () => {
    window.__TAURI_INTERNALS__ = {};
    invoke.mockRejectedValue({
      code: "engine_unavailable",
      message: "internal details must not be shown",
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Temper could not open its local state.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeEnabled();
    expect(screen.queryByText(/Temper is active/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Kairn")).not.toBeInTheDocument();
    expect(screen.queryByText("Green Meadow")).not.toBeInTheDocument();
    expect(document.querySelector(".window-dragbar")).toBeNull();
  });

  it("routes a genuinely unconfigured engine into live onboarding", async () => {
    window.__TAURI_INTERNALS__ = {};
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(false);
      if (command === "setup_status") return response(setup, digest);
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Set up Temper",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Kairn")).not.toBeInTheDocument();
    expect(screen.queryByText("Green Meadow")).not.toBeInTheDocument();
    expect(document.querySelector(".window-dragbar")).toBeNull();
  });

  it("renders only live projects and changes the selected project view", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(snapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Learning",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Temper is active/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Kairn")).not.toBeInTheDocument();
    expect(screen.queryByText("Green Meadow")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Workspace: All projects" }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Beta/i }));
    expect(
      screen.getByRole("button", { name: "Workspace: Beta" }),
    ).toBeInTheDocument();
  });

  it("surfaces a blocking native conflict without exposing the full source", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    const environment = {
      summary_version: "1.0.0",
      project_id: "project-alpha",
      target: "codex",
      status: "conflicting",
      source_count: 1,
      skill_count: 0,
      instruction_count: 1,
      blocking_conflict_count: 1,
      semantic_analysis_status: "current",
      last_analyzed_at: "2026-08-28T12:00:00Z",
      environment_digest: digest,
      source_chain_digest: digest,
      surface: "codex-cli",
      surface_contract_version: "codex-cli-0.150.0-alpha.8",
      global_sources_enabled: false,
      sources: [
        {
          summary_version: "1.0.0",
          source_id: "source-agents",
          target: "codex",
          kind: "project_instructions",
          display_path: "AGENTS.md",
          scope_summary: "Project project-alpha",
          status: "ready",
          instruction_count: 1,
          skill: false,
          activation_status: "active",
          observed_context_only: true,
          raw_payloads_exposed: false,
        },
      ],
      conflicts: [
        {
          summary_version: "1.0.0",
          conflict_id: "conflict-alpha",
          project_id: "project-alpha",
          target: "codex",
          source_display_path: "AGENTS.md",
          temper_behavior: "Always run the full test suite.",
          native_behavior: "Run only the bounded project checks.",
          severity: "blocking",
          resolution_state: "unresolved",
          rationale:
            "The project instruction conflicts with an approved Temper behavior.",
          raw_payloads_exposed: false,
        },
      ],
      raw_payloads_exposed: false,
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(snapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({
          environments: [environment],
          raw_payloads_exposed: false,
        });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "An instruction conflict needs review.",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/C:\\Users|\/home\//)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review conflict" }));
    expect(
      screen.getByText("Always run the full test suite."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Run only the bounded project checks."),
    ).toBeInTheDocument();
  });

  it("uses the selected project's review count without global contradictions", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    const scopedSnapshot = {
      ...snapshot,
      health: "needs_attention",
      suggestions: [globalSuggestion, betaSuggestion],
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(scopedSnapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "2 suggestions to review." }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Workspace: All projects" }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Alpha/i }));

    expect(
      screen.getByRole("heading", { name: "1 suggestion to review." }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("2 suggestions are waiting for review."),
    ).not.toBeInTheDocument();
  });

  it("gates pending review and managed tasks when consent is expired", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    window.localStorage.setItem("temper.advanced", "true");
    const expiredSnapshot = {
      ...snapshot,
      health: "consent_expired",
      consent: {
        ...snapshot.consent,
        days_remaining: 0,
        renewal_required: true,
      },
      suggestions: [globalSuggestion],
    };
    const readySetup = {
      ...configuredSetup,
      connections: configuredSetup.connections.map((connection) =>
        connection.agent_id === "codex"
          ? {
              ...connection,
              installation_state: "installed",
              authentication_state: "signed_in",
              conformance_state: "compatible",
            }
          : connection,
      ),
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(expiredSnapshot, digest);
      if (command === "setup_status") return response(readySetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Reviewed suggestions need renewed permission.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /review suggestion/i }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advanced" }));
    await user.type(screen.getByLabelText("Task"), "Inspect this fixture.");
    expect(
      screen.getByRole("button", { name: "Run with Temper" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("heading", { name: "Ordinary use in progress" }),
    ).toBeInTheDocument();
  });

  it("distinguishes an unavailable secure store from an actionable queue", async () => {
    window.__TAURI_INTERNALS__ = {};
    const blockedSnapshot = {
      ...snapshot,
      health: "needs_attention",
      suggestions: [globalSuggestion],
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(blockedSnapshot, digest);
      if (command === "setup_status") return response(setup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Secure storage needs attention.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /review suggestion/i }),
    ).not.toBeInTheDocument();
  });

  it("reports an installed signed-out Claude connection truthfully", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    const detectedSetup = {
      ...configuredSetup,
      connections: configuredSetup.connections.map((connection) =>
        connection.agent_id === "claude"
          ? {
              ...connection,
              installation_state: "installed",
              authentication_state: "signed_out",
              conformance_state: "compatible",
              status_summary: "Claude Code is installed.",
            }
          : connection,
      ),
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(snapshot, digest);
      if (command === "setup_status") return response(detectedSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    await screen.findByRole("heading", {
      name: "Learning",
    });
    await user.click(screen.getByRole("button", { name: "Connections" }));

    expect(screen.getByText("Sign-in required")).toBeInTheDocument();
    expect(screen.queryByText("Ready to connect")).not.toBeInTheDocument();
  });

  it("connects Claude only after an exact preview and explicit consent", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    let connected = false;
    const readySetup = {
      ...configuredSetup,
      connections: configuredSetup.connections.map((connection) =>
        connection.agent_id === "claude"
          ? {
              ...connection,
              installation_state: "installed",
              authentication_state: "signed_in",
              conformance_state: "compatible",
              integration_state: "available",
              status_summary: "Ready for local connection review.",
              learning_capability: "Available after connection.",
              delivery_capability: "Available after connection.",
              available_actions: ["refresh", "connect"],
            }
          : connection,
      ),
    };
    const connectedSetup = {
      ...readySetup,
      connections: readySetup.connections.map((connection) =>
        connection.agent_id === "claude"
          ? {
              ...connection,
              integration_state: "connected",
              status_summary: "Connected for registered projects.",
              available_actions: ["refresh", "disconnect"],
            }
          : connection,
      ),
    };
    invoke.mockImplementation(async (command: string, args?: unknown) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(snapshot, digest);
      if (command === "setup_status")
        return response(connected ? connectedSetup : readySetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      if (command === "claude_connection_preview")
        return response({
          preview_version: "1.0.0",
          operation: "connect",
          settings: {
            preview_version: "1.0.0",
            preview_token: "claude-preview",
            operation: "install",
            before_digest: digest,
            after_digest: `sha256:${"b".repeat(64)}`,
            before_existed: false,
            after_existed: true,
            helper_digest: `sha256:${"c".repeat(64)}`,
            events: ["SessionEnd", "Stop", "StopFailure", "UserPromptSubmit"],
            redacted_diff: "+ Temper hook helper",
            expires_at: "2026-09-05T12:15:00Z",
            modifies_only_user_settings: true,
            provider_authentication_changed: false,
            provider_call_required: false,
            raw_paths_exposed: false,
          },
          project_ids: ["project-alpha", "project-beta"],
          current_connection_digest: null,
          consent_expires_at: "2026-10-05T12:00:00Z",
          retention_until: "2026-10-05T12:00:00Z",
          learning_enabled: true,
          delivery_enabled: true,
          provider_call_required: false,
          provider_authentication_changed: false,
          raw_paths_exposed: false,
        });
      if (command === "claude_connection_apply") {
        expect(args).toMatchObject({
          previewToken: "claude-preview",
          expectedBeforeDigest: digest,
          consentConfirmed: true,
          expectedSnapshotDigest: digest,
        });
        connected = true;
        return response({
          receipt_id: "claude-connection-one",
          operation: "connect",
          connection_digest: `sha256:${"d".repeat(64)}`,
          expires_at: "2026-10-05T12:00:00Z",
          project_count: 2,
          restart_required: true,
          provider_call_required: false,
          raw_payloads_exposed: false,
        });
      }
      if (command === "target_authorization_preview") {
        expect(args).toMatchObject({
          projectId: "project-alpha",
          targetFamily: "claude-code",
        });
        return response({
          preview_version: "1.0.0",
          preview_token: "portable-preview",
          subject_id: "subject-one",
          project_id: "project-alpha",
          target_family: "claude-code",
          source_release_digest: digest,
          current_authorization_digest: null,
          items: [
            {
              artifact_ref: {
                record_id: "behavior-one",
                record_version: "1.0.0",
                content_digest: `sha256:${"e".repeat(64)}`,
              },
              behavior_summary: "Explain the outcome before procedural detail.",
              scope_summary:
                "Core-wide behavior · this authorization applies only here",
              already_compatible: false,
            },
          ],
          currently_authorized_artifact_refs: [],
          expires_at: "2026-09-05T12:10:00Z",
          provider_call_required: false,
          raw_paths_exposed: false,
        });
      }
      if (command === "target_authorization_apply") {
        expect(args).toMatchObject({
          previewToken: "portable-preview",
          selectedArtifactRefs: [
            expect.objectContaining({ record_id: "behavior-one" }),
          ],
          confirmed: true,
          expectedSnapshotDigest: digest,
        });
        return response({
          mutation_version: "1.0.0",
          receipt_id: "portable-receipt",
          decision: "authorize",
          authorization_digest: `sha256:${"f".repeat(64)}`,
          authorized_artifact_count: 1,
          expires_at: "2026-10-05T12:00:00Z",
          provider_call_required: false,
          raw_paths_exposed: false,
        });
      }
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    await screen.findByRole("heading", {
      name: "Learning",
    });
    await user.click(screen.getByRole("button", { name: "Connections" }));
    await user.click(
      screen.getAllByRole("button", { name: "View details" })[1],
    );
    await user.click(screen.getByRole("button", { name: "Review connection" }));

    expect(
      screen.getByText("2 registered projects · no provider call"),
    ).toBeInTheDocument();
    const connectButton = screen.getByRole("button", {
      name: "Connect Claude Code",
    });
    expect(connectButton).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(connectButton);

    expect(
      await screen.findByText(/Connected for registered projects\./),
    ).toBeInTheDocument();

    await user.click(
      screen.getAllByRole("button", { name: "View details" })[1],
    );
    await user.click(
      screen.getAllByRole("button", { name: "Review behaviors" })[0],
    );
    await user.click(
      screen.getByRole("checkbox", {
        name: /Explain the outcome before procedural detail/i,
      }),
    );
    const applySelection = screen.getByRole("button", {
      name: "Apply selection",
    });
    expect(applySelection).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: /Apply this exact Claude-specific selection/i,
      }),
    );
    await user.click(applySelection);

    expect(
      await screen.findByText(/1 Core behavior is now approved for Claude/),
    ).toBeInTheDocument();
  });

  it("counts only typed global and project-applicable Core items", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    const adaptations = [
      ["global", "Shared guidance", emptyScope],
      [
        "beta",
        "Beta guidance",
        { ...emptyScope, project_ids: ["project-beta"] },
      ],
      [
        "repository-only",
        "Repository-only guidance",
        { ...emptyScope, repository_ids: ["unmapped-repository"] },
      ],
    ].map(([id, intent, scope]) => ({
      summary_version: "1.0.0",
      artifact_id: id,
      artifact_version: "1.0.0",
      artifact_digest: digest,
      artifact_type: "preference",
      layer: "permanent_profile",
      intent,
      required_behaviors: [intent],
      scope,
      evidence_count: 1,
      review_at: null,
      expires_at: null,
      available_actions: ["revoke"],
      raw_payloads_exposed: false,
    }));
    const scopedSnapshot = { ...snapshot, adaptations };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(scopedSnapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    await screen.findByRole("heading", {
      name: "Learning",
    });
    await user.click(screen.getByRole("button", { name: "Core" }));
    await user.click(
      screen.getByRole("button", { name: "Workspace: All projects" }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Beta/i }));

    expect(screen.getByText(/2 approved items/)).toBeInTheDocument();
    expect(screen.getAllByText("Shared guidance")).toHaveLength(2);
    expect(screen.getAllByText("Beta guidance")).toHaveLength(2);
    expect(
      screen.queryByText("Repository-only guidance"),
    ).not.toBeInTheDocument();
  });

  it("sends an explicit multi-project narrowing decision to the engine", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    let currentSnapshot = {
      ...snapshot,
      health: "needs_attention",
      suggestions: [globalSuggestion],
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(currentSnapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      if (command === "review_decide") {
        currentSnapshot = { ...snapshot, suggestions: [] };
        return response(
          {
            receipt_version: "1.0.0",
            operation: "review.decide",
            target_id: "review-global",
            message: "Adaptation kept in selected projects.",
            resulting_snapshot_digest: digest,
            raw_payloads_exposed: false,
          },
          digest,
        );
      }
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "1 suggestion to review." }),
    ).toBeInTheDocument();
    await user.click(
      await screen.findByRole("button", { name: /review suggestion/i }),
    );
    await user.click(
      screen.getByRole("button", { name: "Why am I seeing this?" }),
    );
    await user.click(screen.getByLabelText("Beta"));
    await user.click(
      screen.getByRole("button", { name: "Keep in selected projects" }),
    );

    expect(invoke).toHaveBeenCalledWith(
      "review_decide",
      expect.objectContaining({
        decision: "keep_narrowed",
        projectId: null,
        refinedScope: expect.objectContaining({
          project_ids: ["project-alpha", "project-beta"],
        }),
      }),
    );
  });

  it("allows an offered two-project scope to narrow to one project", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    let currentSnapshot = {
      ...snapshot,
      health: "needs_attention",
      suggestions: [twoProjectSuggestion],
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(currentSnapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      if (command === "review_decide") {
        currentSnapshot = { ...snapshot, suggestions: [] };
        return response(
          {
            receipt_version: "1.0.0",
            operation: "review.decide",
            target_id: "review-two-projects",
            message: "Adaptation kept in one project.",
            resulting_snapshot_digest: digest,
            raw_payloads_exposed: false,
          },
          digest,
        );
      }
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: /review suggestion/i }),
    );
    await user.click(
      screen.getByRole("button", { name: "Why am I seeing this?" }),
    );
    expect(
      screen.getByRole("button", { name: "Keep in selected projects" }),
    ).toBeDisabled();
    await user.click(screen.getByLabelText("Beta"));
    await user.click(
      screen.getByRole("button", { name: "Keep in selected projects" }),
    );

    expect(invoke).toHaveBeenCalledWith(
      "review_decide",
      expect.objectContaining({
        decision: "keep_narrowed",
        refinedScope: expect.objectContaining({
          project_ids: ["project-alpha"],
        }),
      }),
    );
  });

  it("shows and can disable an inherited reporting permission", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    let currentSnapshot = {
      ...snapshot,
      aggregate_reporting_enabled: true,
    };
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(currentSnapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      if (command === "preferences_update") {
        currentSnapshot = {
          ...currentSnapshot,
          aggregate_reporting_enabled: false,
        };
        return response(
          {
            receipt_version: "1.0.0",
            operation: "preferences.update",
            target_id: "desktop-preferences",
            message: "Preferences updated.",
            resulting_snapshot_digest: digest,
            raw_payloads_exposed: false,
          },
          digest,
        );
      }
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    await screen.findByRole("heading", {
      name: "Learning",
    });
    await user.click(screen.getByRole("button", { name: "Settings" }));
    const reporting = screen.getByRole("switch", {
      name: "Help improve Temper",
    });
    expect(reporting).toBeChecked();
    await user.click(reporting);

    expect(invoke).toHaveBeenCalledWith(
      "preferences_update",
      expect.objectContaining({
        preferences: expect.objectContaining({
          aggregateReportingEnabled: false,
        }),
      }),
    );
    expect(
      await screen.findByRole("switch", { name: "Help improve Temper" }),
    ).not.toBeChecked();
  });

  it("does not enable notifications when device permission is denied", async () => {
    const user = userEvent.setup();
    window.__TAURI_INTERNALS__ = {};
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get") return response(snapshot, digest);
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      if (command === "notification_permission") return "denied";
      throw new Error(`Unexpected command: ${command}`);
    });

    render(<App />);
    await screen.findByRole("heading", {
      name: "Learning",
    });
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(
      screen.getByRole("switch", { name: "Review notifications" }),
    );

    expect(
      await screen.findByText(/did not grant permission/i),
    ).toBeInTheDocument();
    expect(
      invoke.mock.calls.some(([command]) => command === "preferences_update"),
    ).toBe(false);
  });

  it("keeps active habit learning distinct from paused reviewed suggestions", async () => {
    window.__TAURI_INTERNALS__ = {};
    const user = userEvent.setup();
    invoke.mockImplementation(async (command: string) => {
      if (command === "engine_handshake") return handshake(true);
      if (command === "snapshot_get")
        return response(
          {
            ...snapshot,
            health: "paused",
            background_enabled: false,
            suggestions: [],
          },
          digest,
        );
      if (command === "setup_status") return response(configuredSetup, digest);
      if (command === "modes_list")
        return response({ modes: [], raw_payloads_exposed: false });
      if (command === "instruction_environment_get")
        return response({ environments: [], raw_payloads_exposed: false });
      if (command === "package_review_list")
        return response({
          items: [],
          pending_count: 0,
          raw_payloads_exposed: false,
        });
      if (command === "autonomy_status")
        return response(
          {
            grant_enabled: true,
            learning_enabled: true,
            personalization_enabled: false,
            automatic_serving_ready: false,
            secure_store_ready: true,
            provenance_state: "owner_authorized",
            input_policy: "owner_authorized_conversations",
            capture_state: "ready",
            mode: "shadow",
            published: false,
            delivery_confirmed: false,
            publication_needs_attention: false,
            habits: [],
            recent_changes: [],
            raw_payloads_exposed: false,
          },
          digest,
        );
      throw new Error(`Unexpected command: ${command}`);
    });
    render(<App />);
    expect(
      await screen.findByRole("button", { name: "Pause learning" }),
    ).toBeEnabled();
    expect(
      screen.getByText("Reviewed suggestions", { selector: "summary" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No new learning is running."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Learning is paused.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(
      screen.getByRole("switch", { name: "Reviewed suggestions" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("switch", { name: "Background learning" }),
    ).not.toBeInTheDocument();
  });
});
