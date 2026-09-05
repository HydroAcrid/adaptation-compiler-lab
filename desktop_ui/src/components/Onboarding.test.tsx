import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const engine = vi.hoisted(() => ({
  adoptExistingInstallation: vi.fn(),
  initializeSetup: vi.fn(),
  previewExistingInstallation: vi.fn(),
  previewSetupProject: vi.fn(),
}));

vi.mock("../engine", () => engine);

import type { EngineSetupSnapshot } from "../engine";
import { Onboarding } from "./Onboarding";

const digest = `sha256:${"a".repeat(64)}`;
const setupSnapshot: EngineSetupSnapshot = {
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
      integration_state: "connected",
      agent_id: "codex",
      display_name: "Codex",
      installation_state: "installed",
      authentication_state: "signed_in",
      conformance_state: "compatible",
      version_label: "codex-cli 0.150.0-alpha.8",
      status_summary: "Ready to use with Temper.",
      learning_capability: "Eligible completed tasks after registration.",
      delivery_capability: "Fresh Temper-managed Codex tasks only.",
      cost_posture: "Uses saved ChatGPT authentication.",
      available_actions: ["refresh", "use_for_setup"],
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
      status_summary: "Claude Code is not installed.",
      learning_capability: "Not integrated in this build.",
      delivery_capability: "Not integrated in this build.",
      cost_posture: "Future Claude use would be provider-billed.",
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("native onboarding progress", () => {
  it("replaces the disabled review screen with two truthful setup stages", async () => {
    const user = userEvent.setup();
    let resolveInitialization!: (value: {
      subject_id: string;
      signer_fingerprint: string;
      project_id: string;
      capture_after_epoch_seconds: number;
      consent_expires_at: string;
    }) => void;
    let resolveOpening!: () => void;
    const initialization = new Promise<{
      subject_id: string;
      signer_fingerprint: string;
      project_id: string;
      capture_after_epoch_seconds: number;
      consent_expires_at: string;
    }>((resolve) => {
      resolveInitialization = resolve;
    });
    const opening = new Promise<void>((resolve) => {
      resolveOpening = resolve;
    });
    engine.previewSetupProject.mockResolvedValue({
      preview_version: "1.0.0",
      preview_token: "opaque-project",
      project_id: "my-portfolio",
      display_name: "my-portfolio",
      capture_after_epoch_seconds: 1_788_000_000,
      expires_at: "2026-08-28T12:00:00Z",
      historical_tasks_eligible: false,
      raw_payloads_exposed: false,
    });
    engine.initializeSetup.mockReturnValue(initialization);

    render(
      <Onboarding
        nativeRuntime
        onComplete={() => opening}
        setupDigest={digest}
        setupSnapshot={setupSnapshot}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(
      screen.getByRole("button", { name: "+ Choose a project" }),
    );
    expect(await screen.findByText("my-portfolio")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(
      screen.getByRole("switch", {
        name: "Allow Temper to learn in this project",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Open Temper" }));

    expect(
      screen.getByRole("heading", { name: "Creating your Temper" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
    expect(screen.queryByText("Finishing…")).not.toBeInTheDocument();

    await act(async () => {
      resolveInitialization({
        subject_id: "temper-test",
        signer_fingerprint: digest,
        project_id: "my-portfolio",
        capture_after_epoch_seconds: 1_788_000_000,
        consent_expires_at: "2026-09-27T12:00:00Z",
      });
      await initialization;
    });

    expect(
      await screen.findByRole("heading", { name: "Opening Temper" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Step 2 of 2")).toBeInTheDocument();

    await act(async () => {
      resolveOpening();
      await opening;
    });
  });
});
