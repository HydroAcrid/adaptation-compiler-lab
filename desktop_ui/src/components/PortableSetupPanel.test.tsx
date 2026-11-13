import { invoke } from "@tauri-apps/api/core";
import {
  cleanup,
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
  const dialog = within(await screen.findByRole("dialog"));
  await user.type(dialog.getByLabelText("Setup name"), setup.title);
  await user.click(dialog.getByRole("button", { name: "Add item" }));
  await user.type(dialog.getByLabelText("Item name"), "Triage");
  await user.type(
    dialog.getByLabelText("Skill guidance"),
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
});

it("recovers from a bad file and requires consent for the exact target and all four reviewed items", async () => {
  let active: SetupPreview | null = null;
  let attempts = 0;
  native.mockImplementation(async (command) => {
    if (command === "tools_hub_request")
      return response({ projects: [repository] });
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
  await screen.findByText("No active portable setups.");
  await user.click(screen.getByRole("button", { name: "Open setup" }));
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

  await user.click(screen.getByRole("button", { name: "Open setup" }));
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
  expect(await screen.findByText("No active portable setups.")).toBeVisible();
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
    .mockResolvedValueOnce(response({ projects: [repository] }))
    .mockResolvedValueOnce(response({ active: null }));
  const user = userEvent.setup();
  render(<PortableSetupPanel nativeRuntime />);
  expect(screen.getByText("Loading portable setups…")).toBeVisible();
  expect(screen.getByRole("button", { name: "Open setup" })).toBeDisabled();
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
  expect(await screen.findByText("No active portable setups.")).toBeVisible();
});
