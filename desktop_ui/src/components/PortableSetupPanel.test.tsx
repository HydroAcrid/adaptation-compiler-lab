import { invoke } from "@tauri-apps/api/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ENGINE_PROTOCOL_VERSION } from "../engine";
import type { SetupPreview } from "../portableSetup";
import { PortableSetupPanel } from "./PortableSetupPanel";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
const native = vi.mocked(invoke);
const repository = {
  id: "fictional-repo",
  label: "Example repository",
  root: "C:/fictional/example",
  active: [],
  paused: false,
  pending_recovery: false,
};
const workflowState = {
  version: 1 as const,
  digest: "fixture",
  enabled: true,
  indexed: true,
  bridge_configured: true,
  native_hooks_configured: true,
  paused: false,
  project_count: 1,
  projects: [repository],
  manager: "fixture",
  manager_ready: true,
  sources: [],
  cleanup_pending: false,
  last_checked: null,
  job: null,
};
const setup: SetupPreview = {
  title: "Release routine",
  digest: "sha256:release",
  signer_fingerprint: "sha256:sender",
  items: [
    {
      id: "skill",
      kind: "skill",
      title: "Triage",
      text: "Read recent changes",
    },
    {
      id: "knowledge",
      kind: "knowledge",
      title: "Docs",
      text: "Docs live here",
    },
    {
      id: "preference",
      kind: "preference",
      title: "Style",
      text: "Use plain language",
    },
    {
      id: "check",
      kind: "check",
      title: "Readiness",
      path: "docs/release.md",
      operation: "file_contains",
      text: "READY",
    },
  ],
};

function response(result: object) {
  return { protocol_version: ENGINE_PROTOCOL_VERSION, ok: true, result };
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("explains desktop availability without fake file controls", () => {
  render(<PortableSetupPanel nativeRuntime={false} />);
  expect(
    screen.getByText(
      "Portable setup files are available in the installed desktop app.",
    ),
  ).toBeVisible();
  expect(screen.queryByRole("button")).toBeNull();
  expect(native).not.toHaveBeenCalled();
});

it("preserves the compose draft through review failure, back, and picker cancellation", async () => {
  let reviewAttempts = 0;
  let saves = 0;
  native.mockImplementation(async (command) => {
    if (command === "tools_hub_request") return response({ projects: [] });
    if (command === "portable_setup_export_preview") {
      if (reviewAttempts++ === 0)
        return {
          ...response({}),
          ok: false,
          error: { message: "Setup preview unavailable." },
        };
      return response({ ...setup, items: [setup.items[0]] });
    }
    if (command === "portable_setup_export") {
      if (saves++ === 0) throw { code: "cancelled" };
      return response(setup);
    }
    throw new Error(command);
  });
  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  await user.tab();
  const create = screen.getByRole("button", { name: "Create setup" });
  expect(create).toHaveFocus();
  await user.keyboard("{Enter}");
  let dialog = within(await screen.findByRole("dialog"));
  await user.type(dialog.getByLabelText("Setup name"), setup.title);
  await user.click(dialog.getByRole("button", { name: "Add item" }));
  await user.type(dialog.getByLabelText("Item name"), "Triage");
  await user.type(
    dialog.getByLabelText("Skill guidance"),
    "Read recent changes",
  );
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  const resume = screen.getByRole("button", { name: "Resume setup draft" });
  await waitFor(() => expect(resume).toHaveFocus());
  await user.keyboard("{Enter}");
  dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByLabelText("Setup name")).toHaveValue(setup.title);
  expect(dialog.getByLabelText("Item name")).toHaveValue("Triage");
  expect(dialog.getByLabelText("Skill guidance")).toHaveValue(
    "Read recent changes",
  );
  await user.click(dialog.getByRole("button", { name: "Review setup" }));
  expect(await dialog.findByRole("alert")).toHaveTextContent(
    "Setup preview unavailable.",
  );
  expect(dialog.getByLabelText("Skill guidance")).toHaveValue(
    "Read recent changes",
  );
  await user.click(dialog.getByRole("button", { name: "Review setup" }));
  expect(
    await dialog.findByRole("heading", { name: "Review before saving" }),
  ).toHaveFocus();
  await user.click(dialog.getByRole("button", { name: "Back to edit" }));
  expect(dialog.getByLabelText("Setup name")).toHaveFocus();
  expect(dialog.getByLabelText("Item name")).toHaveValue("Triage");
  await user.click(dialog.getByRole("button", { name: "Review setup" }));
  await user.click(
    await dialog.findByRole("button", { name: "Save setup file" }),
  );
  expect(dialog.queryByRole("alert")).toBeNull();
  await user.click(dialog.getByRole("button", { name: "Save setup file" }));
  expect(await screen.findByText("Saved “Release routine”.")).toBeVisible();
  await waitFor(() => expect(create).toHaveFocus());
  await user.keyboard("{Enter}");
  dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByLabelText("Setup name")).toHaveValue("");
  expect(dialog.queryByLabelText("Skill guidance")).toBeNull();
});

it("recovers from a bad file and requires consent for the exact target and all four reviewed items", async () => {
  let active: SetupPreview | null = null;
  let attempts = 0;
  native.mockImplementation(async (command) => {
    if (command === "tools_hub_request") return response(workflowState);
    if (command === "portable_setup_status") return response({ active });
    if (command === "portable_setup_import_preview") {
      if (attempts++ === 0)
        return {
          ...response({}),
          ok: false,
          error: { message: "The signature could not be verified." },
        };
      return response({
        ...setup,
        project_id: repository.id,
        source_name: "routine.temper-setup",
        active_digest: active?.digest ?? null,
      });
    }
    if (command === "portable_setup_import_approve") {
      active = setup;
      return response(setup);
    }
    if (command === "portable_setup_remove") {
      active = null;
      return response({ active });
    }
    throw new Error(command);
  });
  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  await screen.findByText("No setup imported");
  await user.click(screen.getByRole("button", { name: "Import setup" }));
  const dialog = within(await screen.findByRole("dialog"));
  expect(
    dialog.getByRole("button", { name: "Choose setup file" }),
  ).toBeDisabled();
  await user.click(dialog.getByRole("combobox", { name: "Target repository" }));
  await user.click(screen.getByRole("option", { name: /Example repository/ }));
  await user.click(dialog.getByRole("button", { name: "Choose setup file" }));
  expect(await dialog.findByRole("alert")).toHaveTextContent(
    "The signature could not be verified.",
  );
  await user.click(dialog.getByRole("button", { name: "Choose setup file" }));
  expect(await dialog.findByText("routine.temper-setup")).toBeVisible();
  for (const item of setup.items) {
    expect(dialog.getByText(item.title)).toBeVisible();
    expect(dialog.getByText(item.text!)).toBeVisible();
  }
  expect(dialog.getByText(repository.root)).toBeVisible();
  expect(dialog.getByRole("button", { name: "Apply setup" })).toBeDisabled();
  await user.click(dialog.getByRole("checkbox", { name: /approve applying/ }));
  await user.click(dialog.getByRole("button", { name: "Apply setup" }));
  expect(native).toHaveBeenCalledWith("portable_setup_import_approve", {
    projectId: repository.id,
    digest: setup.digest,
    activeDigest: null,
    idempotencyKey: expect.any(String),
  });
  expect(
    await screen.findByText(
      "“Release routine” is active in Example repository.",
    ),
  ).toBeVisible();
  await user.click(await screen.findByText("View setup contents"));
  expect(screen.getByText("Read recent changes")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "Import setup" }));
  const replacement = within(await screen.findByRole("dialog"));
  await user.click(
    replacement.getByRole("combobox", { name: "Target repository" }),
  );
  await user.click(screen.getByRole("option", { name: /Example repository/ }));
  await user.click(
    replacement.getByRole("button", { name: "Choose setup file" }),
  );
  const replace = await replacement.findByRole("button", {
    name: "Replace setup",
  });
  expect(replace).toBeDisabled();
  await user.click(
    replacement.getByRole("checkbox", { name: /approve replacing/ }),
  );
  await user.click(replace);
  expect(native).toHaveBeenCalledWith("portable_setup_import_approve", {
    projectId: repository.id,
    digest: setup.digest,
    activeDigest: setup.digest,
    idempotencyKey: expect.any(String),
  });
  await user.click(await screen.findByText("View setup contents"));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Remove setup" })).toBeEnabled(),
  );
  await user.click(screen.getByRole("button", { name: "Remove setup" }));
  const remove = within(await screen.findByRole("dialog"));
  await user.click(remove.getByRole("button", { name: "Keep setup" }));
  expect(native).not.toHaveBeenCalledWith(
    "portable_setup_remove",
    expect.anything(),
  );
  await user.click(screen.getByRole("button", { name: "Remove setup" }));
  await user.click(
    within(await screen.findByRole("dialog")).getByRole("button", {
      name: "Remove setup",
    }),
  );
  expect(await screen.findByText("No setup imported")).toBeVisible();
});

it("keeps a status failure retryable and shows that setup status is loading", async () => {
  let resolveFirst: ((value: object) => void) | undefined;
  native
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    )
    .mockResolvedValueOnce(response(workflowState))
    .mockResolvedValueOnce(response({ active: null }));
  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  expect(screen.getByText("Loading repository setups…")).toBeVisible();
  expect(screen.getByRole("button", { name: "Import setup" })).toBeDisabled();
  resolveFirst?.({
    ...response({}),
    ok: false,
    error: { message: "Could not load repositories." },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not load repositories.",
  );
  await user.click(
    screen.getByRole("button", { name: "Refresh repositories" }),
  );
  expect(await screen.findByText("No setup imported")).toBeVisible();
});

it("requires confirmation to clear an unreadable setup and refreshes after a stale recovery", async () => {
  let unreadable = true;
  let attempts = 0;
  const recoveryDigest = "sha256:unreadable";
  native.mockImplementation(async (command) => {
    if (command === "tools_hub_request") return response(workflowState);
    if (command === "portable_setup_status")
      return response(
        unreadable
          ? {
              active: null,
              issue: "unavailable",
              recovery_digest: recoveryDigest,
            }
          : { active: null },
      );
    if (command === "portable_setup_reset") {
      if (attempts++ === 0)
        return {
          ...response({}),
          ok: false,
          error: {
            message:
              "The unreadable setup changed. Refresh before trying again.",
          },
        };
      unreadable = false;
      return response({ active: null });
    }
    throw new Error(command);
  });
  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  const trigger = await screen.findByRole("button", {
    name: "Clear unreadable setup",
  });
  expect(screen.getByRole("alert")).toHaveTextContent("could not verify");
  await user.click(trigger);
  let dialog = within(await screen.findByRole("dialog"));
  await user.click(dialog.getByRole("button", { name: "Cancel" }));
  expect(native).not.toHaveBeenCalledWith(
    "portable_setup_reset",
    expect.anything(),
  );
  await user.click(trigger);
  dialog = within(await screen.findByRole("dialog"));
  await user.click(
    dialog.getByRole("button", { name: "Clear unreadable setup" }),
  );
  expect(await dialog.findByRole("alert")).toHaveTextContent("changed");
  await user.click(dialog.getByRole("button", { name: "Cancel" }));
  await user.click(
    screen.getByRole("button", { name: "Refresh repositories" }),
  );
  await waitFor(() => expect(trigger).toBeEnabled());
  await user.click(trigger);
  dialog = within(await screen.findByRole("dialog"));
  await user.click(
    dialog.getByRole("button", { name: "Clear unreadable setup" }),
  );
  expect(native).toHaveBeenCalledWith("portable_setup_reset", {
    projectId: repository.id,
    digest: recoveryDigest,
    idempotencyKey: expect.any(String),
  });
  expect(await screen.findByText("No setup imported")).toBeVisible();
});

it("blocks paused and disconnected setup imports before file selection", async () => {
  native.mockResolvedValue(response({ active: null }));
  const state = workflowState;
  function panel(overrides: Partial<typeof state>) {
    return (
      <PortableSetupPanel
        nativeRuntime
        status={{
          state: { ...state, ...overrides },
          pending: false,
          failed: false,
          revision: 0,
          refresh: vi.fn(),
        }}
      />
    );
  }

  const user = userEvent.setup();
  const { rerender } = render(panel({ paused: true }));
  expect(
    await screen.findByText("Resume updates to import a setup."),
  ).toBeVisible();
  const trigger = screen.getByRole("button", { name: "Import setup" });
  expect(trigger).toBeDisabled();
  rerender(panel({ bridge_configured: false }));
  expect(screen.getByText("Connect Codex to import a setup.")).toBeVisible();
  expect(trigger).toBeDisabled();
  rerender(panel({ projects: [{ ...repository, paused: true }] }));
  expect(
    screen.getByText("Resume updates for this repository to import a setup."),
  ).toBeVisible();
  expect(trigger).toBeDisabled();
  expect(native).not.toHaveBeenCalledWith(
    "portable_setup_import_preview",
    expect.anything(),
  );

  rerender(panel({}));
  await user.click(trigger);
  const dialog = within(await screen.findByRole("dialog"));
  await user.click(dialog.getByRole("combobox", { name: "Target repository" }));
  await user.click(screen.getByRole("option", { name: /Example repository/ }));
  expect(
    dialog.getByRole("button", { name: "Choose setup file" }),
  ).toBeEnabled();
  rerender(panel({ paused: true }));
  expect(
    dialog.getByRole("button", { name: "Choose setup file" }),
  ).toBeDisabled();
  expect(dialog.getByText("Resume updates to import a setup.")).toBeVisible();
});

it("shares an approved repository setup with its real contents and protects an existing draft", async () => {
  native.mockImplementation(async (command) => {
    if (command === "tools_hub_request") return response(workflowState);
    if (command === "portable_setup_status") return response({ active: setup });
    if (command === "portable_setup_export_preview") return response(setup);
    throw new Error(command);
  });
  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  const share = await screen.findByRole("button", {
    name: "Share setup for Example repository",
  });
  expect(share).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Create setup" }));
  let dialog = within(await screen.findByRole("dialog"));
  await user.type(dialog.getByLabelText("Setup name"), "Unrelated setup");
  await user.keyboard("{Escape}");
  expect(share).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Resume setup draft" }));
  dialog = within(await screen.findByRole("dialog"));
  await user.click(dialog.getByRole("button", { name: "Discard draft" }));
  expect(share).toBeEnabled();
  await user.click(share);
  dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByLabelText("Setup name")).toHaveValue(setup.title);
  expect(dialog.getByLabelText("Skill guidance")).toHaveValue(
    "Read recent changes",
  );
  expect(dialog.getByLabelText("Knowledge text")).toHaveValue("Docs live here");
  expect(dialog.getByLabelText("Preference text")).toHaveValue(
    "Use plain language",
  );
  expect(dialog.getByLabelText("Text to find")).toHaveValue("READY");
  await user.click(dialog.getByRole("button", { name: "Review setup" }));
  expect(native).toHaveBeenCalledWith("portable_setup_export_preview", {
    title: setup.title,
    items: setup.items,
  });
});

it("keeps all last verified items during a pending and failed refresh, then recovers", async () => {
  let settleRefresh: ((value: unknown) => void) | undefined;
  let reads = 0;
  native.mockImplementation(async (command) => {
    if (command === "tools_hub_request") return response(workflowState);
    if (command !== "portable_setup_status") throw new Error(command);
    if (++reads === 2) {
      return new Promise((resolve) => {
        settleRefresh = resolve;
      });
    }
    return response({ active: reads === 1 ? setup : null });
  });
  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  const panel = within(
    screen.getByRole("region", { name: "Repository setup" }),
  );
  const share = await panel.findByRole("button", {
    name: "Share setup for Example repository",
  });
  expect(panel.getByText(setup.items[0].title)).not.toBeVisible();
  await user.click(panel.getByText("View setup contents"));
  const remove = panel.getByRole("button", { name: "Remove setup" });
  const importSetup = panel.getByRole("button", { name: "Import setup" });
  const refresh = panel.getByRole("button", { name: "Refresh repositories" });
  expect(share).toBeEnabled();
  expect(remove).toBeEnabled();
  expect(importSetup).toBeEnabled();

  await user.click(refresh);
  expect(panel.getByText("Refreshing repository setups…")).toBeVisible();
  for (const item of setup.items) {
    expect(panel.getByText(item.title)).toBeVisible();
  }
  expect(remove).toBeDisabled();

  settleRefresh?.({
    ...response({}),
    ok: false,
    error: { message: "This repository could not be reached." },
  });
  expect(
    await panel.findByText("Last known setup · Release routine"),
  ).toBeVisible();
  expect(panel.getByRole("alert")).toHaveTextContent(
    "This repository could not be reached.",
  );
  for (const item of setup.items) {
    expect(panel.getByText(item.title)).toBeVisible();
  }
  expect(share).toBeDisabled();
  expect(remove).toBeDisabled();
  expect(importSetup).toBeDisabled();

  await user.click(panel.getByRole("button", { name: "Refresh repositories" }));
  expect(await panel.findByText("No setup imported")).toBeVisible();
  expect(panel.queryByText(/Last known setup/)).toBeNull();
  expect(panel.queryByText("Readiness")).toBeNull();
  expect(importSetup).toBeEnabled();
});

it("reviews a workflow update before applying it and restores the previous setup while the source is unavailable", async () => {
  const candidate = {
    ...setup,
    digest: "sha256:new-release",
    items: setup.items.map((item) =>
      item.kind === "check" ? { ...item, text: "SHIPPED" } : item,
    ),
  };
  let active = setup;
  let sourceIssue = false;
  let approveAttempts = 0;
  const approvalKeys: unknown[] = [];
  native.mockImplementation(async (command, args) => {
    if (command === "tools_hub_request") return response(workflowState);
    if (command === "portable_setup_status") return response({ active });
    expect(args).toMatchObject({ projectId: repository.id });
    if (command === "portable_setup_update_status")
      return response({
        connected: true,
        available: !sourceIssue && active.digest === setup.digest,
        can_rollback: active.digest === candidate.digest,
        ...(sourceIssue ? { issue: "The update folder is unavailable." } : {}),
      });
    if (command === "portable_setup_update_preview")
      return response({
        ...candidate,
        project_id: repository.id,
        source_name: "workflow.temper-setup",
        active_digest: setup.digest,
        review_id: "exact-update",
        direction: "update",
        baseline_passed: 1,
        candidate_passed: 2,
        assertion_count: 2,
      });
    if (command === "portable_setup_update_rollback_preview")
      return response({
        ...setup,
        project_id: repository.id,
        source_name: "Previous setup",
        active_digest: candidate.digest,
        review_id: "exact-restore",
        direction: "rollback",
      });
    if (command === "portable_setup_update_approve") {
      const request = args as { reviewId: string; idempotencyKey: string };
      expect(request.idempotencyKey).toBeTruthy();
      approvalKeys.push(request.idempotencyKey);
      if (request.reviewId === "exact-restore") active = setup;
      else {
        expect(request.reviewId).toBe("exact-update");
        if (approveAttempts++ === 0)
          throw { code: "busy", message: "Temper is busy. Try again." };
        active = candidate;
        sourceIssue = true;
      }
      return response(active);
    }
    throw new Error(command);
  });

  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  const reviewUpdate = await screen.findByRole("button", {
    name: "Review update",
  });
  await user.click(reviewUpdate);
  let dialog = within(
    await screen.findByRole("dialog", { name: "Review workflow update" }),
  );
  expect(dialog.getByText(repository.root)).toBeVisible();
  expect(dialog.getByText("SHIPPED", { selector: "dd" })).toBeVisible();
  expect(dialog.getByText("1 of 2 correct")).toBeVisible();
  expect(dialog.getByText("2 of 2 correct")).toBeVisible();
  expect(
    dialog.getByRole("button", { name: "Apply workflow update" }),
  ).toBeEnabled();
  expect(approvalKeys).toHaveLength(0);
  await user.keyboard("{Escape}");
  await waitFor(() => expect(reviewUpdate).toHaveFocus());
  expect(approvalKeys).toHaveLength(0);

  await user.click(reviewUpdate);
  dialog = within(await screen.findByRole("dialog"));
  await user.click(
    dialog.getByRole("button", { name: "Apply workflow update" }),
  );
  expect(await dialog.findByRole("alert")).toHaveTextContent("Temper is busy");
  await user.click(
    dialog.getByRole("button", { name: "Apply workflow update" }),
  );
  expect(
    await screen.findByText("Updated “Release routine” in Example repository."),
  ).toBeVisible();
  expect(approvalKeys).toHaveLength(2);
  expect(approvalKeys[1]).toBe(approvalKeys[0]);
  expect(
    await screen.findByText("The update folder is unavailable."),
  ).toBeVisible();
  await user.click(
    await screen.findByRole("button", { name: "Review previous setup" }),
  );
  dialog = within(
    await screen.findByRole("dialog", { name: "Review previous setup" }),
  );
  expect(dialog.getByText("READY", { selector: "dd" })).toBeVisible();
  await user.click(
    dialog.getByRole("button", { name: "Restore previous setup" }),
  );
  expect(
    await screen.findByText(
      "Restored “Release routine” in Example repository.",
    ),
  ).toBeVisible();
  expect(approvalKeys[2]).not.toBe(approvalKeys[0]);
});

it("retries update checks, tolerates picker cancellation, and checks again on focus", async () => {
  let checks = 0;
  let connected = false;
  let picks = 0;
  let available = false;
  native.mockImplementation(async (command, args) => {
    if (command === "tools_hub_request") return response(workflowState);
    if (command === "portable_setup_status") return response({ active: setup });
    expect(args).toMatchObject({ projectId: repository.id });
    if (command === "portable_setup_update_status") {
      if (checks++ === 0) throw { code: "engine_unavailable" };
      return response({ connected, available, can_rollback: false });
    }
    if (command === "portable_setup_update_source") {
      expect(args).toMatchObject({ idempotencyKey: expect.any(String) });
      if (picks++ === 0) throw { code: "cancelled" };
      connected = true;
      return response({ connected });
    }
    if (command === "portable_setup_update_disconnect") {
      expect(args).toMatchObject({ idempotencyKey: expect.any(String) });
      connected = false;
      available = false;
      return response({ connected });
    }
    throw new Error(command);
  });

  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  await user.click(
    await screen.findByRole("button", { name: "Retry update check" }),
  );
  expect(await screen.findByText("No update source connected.")).toBeVisible();
  const connect = screen.getByRole("button", { name: "Connect update source" });
  await user.click(connect);
  await waitFor(() => expect(connect).toBeEnabled());
  expect(screen.queryByRole("alert")).toBeNull();
  await user.click(connect);
  expect(
    await screen.findByRole("button", { name: "Change update source" }),
  ).toBeVisible();
  available = true;
  fireEvent(window, new Event("focus"));
  expect(
    await screen.findByRole("button", { name: "Review update" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Disconnect source" }));
  expect(await screen.findByText("No update source connected.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Review update" })).toBeNull();
});

it("blocks approval when the reviewed repository setup changes", async () => {
  let active = setup;
  const update = { ...setup, digest: "sha256:pending" };
  native.mockImplementation(async (command) => {
    if (command === "portable_setup_status") return response({ active });
    if (command === "portable_setup_update_status")
      return response({
        connected: true,
        available: true,
        can_rollback: false,
      });
    if (command === "portable_setup_update_preview")
      return response({
        ...update,
        project_id: repository.id,
        source_name: "workflow.temper-setup",
        active_digest: setup.digest,
        review_id: "stale-review",
        direction: "update",
      });
    throw new Error(command);
  });
  const user = userEvent.setup();
  const status = {
    state: workflowState,
    pending: false,
    failed: false,
    revision: 1,
    refresh: vi.fn(),
  };
  const { rerender } = render(
    <PortableSetupPanel nativeRuntime status={status} />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Review update" }),
  );
  const dialog = within(await screen.findByRole("dialog"));
  const apply = dialog.getByRole("button", { name: "Apply workflow update" });
  expect(apply).toBeEnabled();
  active = { ...setup, digest: "sha256:external-change" };
  rerender(
    <PortableSetupPanel nativeRuntime status={{ ...status, revision: 2 }} />,
  );
  await waitFor(() => expect(apply).toBeDisabled());
  expect(dialog.getByText(/Close this review/)).toBeVisible();
  expect(
    native.mock.calls.some(
      ([command]) => command === "portable_setup_update_approve",
    ),
  ).toBe(false);
});
