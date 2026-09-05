import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const engine = vi.hoisted(() => ({
  exportRecovery: vi.fn(),
  loadRecoveryExportPreview: vi.fn(),
  loadRecoveryImportPreview: vi.fn(),
  restoreRecovery: vi.fn(),
  selectRecoveryProject: vi.fn(),
}));

vi.mock("../engine", () => engine);

import { RecoveryExportDialog, RecoveryImportDialog } from "./RecoveryDialog";

const preview = {
  preview_version: "1.0.0" as const,
  preview_token: "recovery-preview",
  bundle_id: "temper-recovery-1",
  bundle_digest: `sha256:${"a".repeat(64)}`,
  signer_fingerprint: `sha256:${"b".repeat(64)}`,
  created_at: "2026-09-05T12:00:00Z",
  source_platform: "windows" as const,
  projects: [
    {
      project_id: "kairn",
      display_name: "Kairn",
      source_project_digest: `sha256:${"c".repeat(64)}`,
      capture_after_epoch_seconds: 1,
    },
  ],
  governed_file_count: 3,
  encrypted_raw_file_count: 1,
  total_encrypted_bytes: 2048,
  expires_at: "2026-09-05T12:10:00Z",
  requires_project_rebinding: true as const,
  overwrites_existing_installation: false as const,
  raw_paths_exposed: false as const,
  raw_payloads_exposed: false as const,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("offline recovery dialogs", () => {
  it("previews the exact backup and requires matching passphrases", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    engine.loadRecoveryExportPreview.mockResolvedValue(preview);
    engine.exportRecovery.mockResolvedValue({ status: "exported" });

    render(
      <RecoveryExportDialog
        onComplete={onComplete}
        onOpenChange={vi.fn()}
        open
        snapshotDigest={`sha256:${"d".repeat(64)}`}
      />,
    );

    expect(await screen.findByText("3")).toBeInTheDocument();
    const fields = screen.getAllByLabelText(/passphrase/i);
    await user.type(fields[0]!, "correct horse battery staple");
    await user.type(fields[1]!, "correct horse battery staple");
    await user.click(
      screen.getByRole("button", { name: "Choose where to save" }),
    );

    await waitFor(() => expect(engine.exportRecovery).toHaveBeenCalledOnce());
    expect(engine.exportRecovery.mock.calls[0]?.[0]).toEqual(preview);
    expect(onComplete).toHaveBeenCalledWith("Encrypted recovery file created.");
  });

  it("restores only after every project is rebound through an opaque selection", async () => {
    const user = userEvent.setup();
    const selection = {
      selection_token: "project-selection",
      preview_token: preview.preview_token,
      project_id: "kairn",
      display_name: "Kairn local",
      expires_at: preview.expires_at,
      path_exposed: false as const,
    };
    const onRestored = vi.fn();
    engine.loadRecoveryImportPreview.mockResolvedValue(preview);
    engine.selectRecoveryProject.mockResolvedValue(selection);
    engine.restoreRecovery.mockResolvedValue({ configured: true });

    render(
      <RecoveryImportDialog
        onOpenChange={vi.fn()}
        onRestored={onRestored}
        open
        setupDigest={`sha256:${"d".repeat(64)}`}
      />,
    );

    await user.type(
      screen.getByLabelText("Recovery passphrase"),
      "correct horse battery staple",
    );
    await user.click(
      screen.getByRole("button", { name: "Choose recovery file" }),
    );
    expect(
      await screen.findByText("Project folder required"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Restore Temper" }),
    ).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Choose folder" }));
    expect(await screen.findByText("Using Kairn local")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restore Temper" }));

    await waitFor(() => expect(engine.restoreRecovery).toHaveBeenCalledOnce());
    expect(engine.restoreRecovery.mock.calls[0]?.[1]).toEqual({
      kairn: selection,
    });
    expect(onRestored).toHaveBeenCalledOnce();
  });
});
