import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ToolsHubPanel } from "./ToolsHubPanel";
import type { HubState } from "../toolsHub";

const api = vi.hoisted(() => ({ hubRequest: vi.fn() }));
vi.mock("../toolsHub", () => api);
const initial: HubState = {
  version: 1,
  digest: "fixture-digest",
  enabled: false,
  paused: false,
  project_count: 0,
  projects: [],
  sources: [
    {
      id: "superpowers",
      label: "Superpowers",
      url: "https://github.com/obra/superpowers",
      approved: false,
    },
  ],
  manager: "SkillKit 1.24.0",
  manager_ready: false,
  indexed: false,
  bridge_configured: false,
  cleanup_pending: false,
  last_checked: null,
  job: null,
};
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
});

it("does not treat learning repositories as tool permission and previews exact destinations", async () => {
  const user = userEvent.setup();
  api.hubRequest.mockImplementation(async (operation: string) => {
    if (operation === "status") return initial;
    if (operation === "inventory")
      return {
        projects: [
          { id: "fixture-id", label: "My repo", root: "/fixture/repo" },
        ],
      };
    if (operation === "permission_preview")
      return {
        preview_id: "fixture-preview",
        projects: [{ id: "fixture-id", root: "/fixture/repo" }],
        destinations: ["/fixture/repo/.agents/skills"],
        manager_destination: "/fixture/private/manager",
      };
    return { status: "running" };
  });
  render(<ToolsHubPanel nativeRuntime />);
  await user.click(
    await screen.findByRole("button", { name: "Set up repository tools" }),
  );
  expect(api.hubRequest).not.toHaveBeenCalledWith(
    "permission_enable",
    expect.anything(),
    expect.anything(),
  );
  await user.click(
    screen.getByRole("checkbox", { name: /My repo.*fixture-id/ }),
  );
  await user.click(screen.getByRole("checkbox", { name: "Superpowers" }));
  await user.click(screen.getByRole("button", { name: "Review setup" }));
  expect(
    await screen.findByRole("dialog", { name: "Allow repository tool setup" }),
  ).toBeVisible();
  expect(screen.getByText("/fixture/repo/.agents/skills")).toBeVisible();
  expect(
    screen.getByText(/This does not authorize chat learning/),
  ).toBeVisible();
  await user.keyboard("{Escape}");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Review setup" })).toHaveFocus(),
  );
  await user.keyboard("{Enter}");
  await screen.findByRole("dialog", { name: "Allow repository tool setup" });
  await user.click(screen.getByRole("button", { name: "Allow and continue" }));
  expect(api.hubRequest).toHaveBeenCalledWith(
    "permission_enable",
    { preview_id: "fixture-preview" },
    initial.digest,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Repository setup" }),
    ).toHaveFocus(),
  );
});

it.each([
  ["Connect Codex", "Connect Codex to repository setup"],
  ["Repair setup", "Repair the private manager"],
  ["Stop managing tools", "Stop managing repository tools"],
])("returns keyboard focus after closing %s", async (opener, title) => {
  const user = userEvent.setup();
  api.hubRequest.mockImplementation(async (operation: string) => {
    if (operation === "status")
      return {
        ...initial,
        enabled: true,
        indexed: true,
        job: { job_id: "fixture", operation: "maintenance", state: "failed" },
      };
    if (operation === "connection_preview")
      return { preview_id: "fictional-connection", files: [] };
    return {};
  });
  render(<ToolsHubPanel nativeRuntime />);
  const trigger = await screen.findByRole("button", {
    name: opener,
    exact: true,
  });
  await user.click(trigger);
  await screen.findByRole("dialog", { name: title });
  await user.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("keeps retained guidance and blocked cleanup visible after permission stops", async () => {
  api.hubRequest.mockResolvedValue({
    ...initial,
    cleanup_pending: true,
    project_count: 1,
    projects: [
      {
        id: "fixture",
        label: "My repo",
        root: "/fixture/repo",
        active: ["debugging"],
        paused: false,
        pending_recovery: false,
      },
    ],
    job: {
      job_id: "fixture",
      operation: "cleanup",
      state: "complete",
      result: {
        status: "stopped",
        projects: [
          {
            project_id: "fixture",
            status: "paused_owner_edit",
            conflicts: [".agents/skills/debugging/SKILL.md"],
          },
        ],
      },
    },
  });
  render(<ToolsHubPanel nativeRuntime />);
  expect(
    await screen.findByRole("heading", { name: "Tool updates have stopped" }),
  ).toBeVisible();
  expect(screen.getByText("My repo (fixture): debugging")).toBeVisible();
  expect(
    screen.getByText("fixture: .agents/skills/debugging/SKILL.md"),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Retry safe cleanup" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Set up repository tools" }),
  ).toBeNull();
});

it("rejects a stale poll after a user action and stays navigable during manager work", async () => {
  const user = userEvent.setup();
  const active = { ...initial, enabled: true, indexed: true, project_count: 1 };
  let release: ((value: HubState) => void) | undefined;
  let poll: (() => void) | undefined;
  const originalInterval = window.setInterval.bind(window);
  vi.spyOn(window, "setInterval").mockImplementation(((
    callback: TimerHandler,
    delay?: number,
  ) => {
    if (delay === 3000) {
      poll = callback as () => void;
      return 1;
    }
    return originalInterval(callback, delay);
  }) as typeof window.setInterval);
  let state = active;
  let hold = false;
  api.hubRequest.mockImplementation(async (operation: string) => {
    if (operation === "status") {
      if (hold) {
        hold = false;
        return new Promise<HubState>((resolve) => {
          release = resolve;
        });
      }
      return state;
    }
    if (operation === "control") {
      state = { ...active, paused: true };
      return { status: "paused" };
    }
    return {};
  });
  render(<ToolsHubPanel nativeRuntime />);
  await screen.findByRole("button", { name: "Pause updates" });
  hold = true;
  await act(async () => {
    poll?.();
  });
  await user.click(screen.getByRole("button", { name: "Pause updates" }));
  await screen.findByRole("button", { name: "Resume updates" });
  await act(async () => release?.(active));
  expect(screen.getByRole("button", { name: "Resume updates" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Pause updates" })).toBeNull();
});

it("shows unknown status instead of claiming approved repos are ready", async () => {
  api.hubRequest.mockRejectedValue(new Error("Secure store is locked"));
  render(<ToolsHubPanel nativeRuntime />);
  expect(await screen.findByText("Status unavailable")).toBeVisible();
  expect(screen.getByRole("alert")).toHaveTextContent("Secure store is locked");
  expect(screen.queryByText("Ready for tasks")).toBeNull();
});

it("keeps a rejected action visible after a successful status refresh", async () => {
  const user = userEvent.setup();
  api.hubRequest.mockImplementation(async (operation: string) => {
    if (operation === "status")
      return { ...initial, enabled: true, indexed: true };
    if (operation === "control")
      throw new Error(
        "Permission changed in another window. Refresh before retrying.",
      );
    return {};
  });
  render(<ToolsHubPanel nativeRuntime />);
  await user.click(
    await screen.findByRole("button", { name: "Pause updates" }),
  );
  await waitFor(() =>
    expect(
      api.hubRequest.mock.calls.filter((call) => call[0] === "status").length,
    ).toBeGreaterThanOrEqual(3),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Permission changed in another window",
  );
});
