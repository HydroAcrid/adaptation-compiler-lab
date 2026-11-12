import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ToolsHubPanel } from "./ToolsHubPanel";
import { PageVisibility } from "../pageVisibility";
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
  vi.useRealTimers();
});

const populated: HubState = {
  ...initial,
  enabled: true,
  indexed: true,
  native_hooks_configured: true,
  project_count: 1,
  sources: [{ ...initial.sources[0], approved: true }],
  projects: [
    {
      id: "fictional-repo",
      label: "Example",
      root: "/fictional-repo",
      paused: false,
      active: ["debugging"],
      pending_recovery: false,
    },
  ],
  last_task: {
    project_id: "fictional-repo",
    state: "complete",
    status: "ready",
  },
  last_checked: 1_793_625_600,
  job: {
    job_id: "fictional-maintenance",
    operation: "maintenance",
    state: "complete",
    result: { status: "indexed", skills: 8 },
  },
};

it("shows repository guidance and the latest task check on the compact Overview", async () => {
  const user = userEvent.setup();
  const openTools = vi.fn();
  api.hubRequest.mockResolvedValue(populated);
  render(<ToolsHubPanel nativeRuntime onOpenTools={openTools} />);

  expect(screen.getByRole("status")).toHaveTextContent(
    "Checking workflow status",
  );
  expect(await screen.findByText("Codex connection configured")).toBeVisible();
  expect(screen.getByText("Example")).toBeVisible();
  expect(screen.getByText(/Available guidance.*debugging/)).toBeVisible();
  expect(
    screen.getByText(/Latest task check.*Example.*Check complete/),
  ).toBeVisible();
  expect(screen.queryByText("How automatic workflows work")).toBeNull();

  await user.click(
    screen.getByRole("button", { name: "View automatic workflows" }),
  );
  expect(openTools).toHaveBeenCalledOnce();
});

it("shows recorded activity and keeps workflow help collapsed on Tools", async () => {
  const user = userEvent.setup();
  api.hubRequest.mockResolvedValue(populated);
  const { container } = render(<ToolsHubPanel nativeRuntime />);

  expect(await screen.findByText("Example · Check complete")).toBeVisible();
  expect(screen.getByText(/Available guidance.*debugging/)).toBeVisible();
  expect(screen.getByText("Superpowers")).toBeVisible();
  expect(screen.getByText("Complete")).toBeVisible();
  expect(container.querySelector("time")).toHaveAttribute(
    "datetime",
    new Date(populated.last_checked! * 1000).toISOString(),
  );
  expect(
    screen.getByRole("button", { name: "Check for updates" }),
  ).toBeEnabled();
  const help = screen.getByText("How automatic workflows work");
  const cleanup = screen.getByText(
    /removes its unchanged copies when a task ends/,
  );
  expect(cleanup).not.toBeVisible();
  await user.click(help);
  expect(cleanup).toBeVisible();
  expect(screen.getByText("/hooks")).toBeVisible();
});

it("keeps guidance visible during maintenance and reports paused updates after refresh", async () => {
  vi.useFakeTimers();
  api.hubRequest
    .mockResolvedValueOnce({
      ...populated,
      job: {
        job_id: "fictional-maintenance",
        operation: "maintenance",
        state: "running",
      },
    })
    .mockResolvedValue({
      ...populated,
      paused: true,
    });
  render(<ToolsHubPanel nativeRuntime />);
  await act(async () => {});
  expect(screen.getByText("Publisher check in progress…")).toBeVisible();
  expect(screen.getByText(/Available guidance.*debugging/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Check for updates" }),
  ).toBeDisabled();

  await act(async () => vi.advanceTimersByTimeAsync(3000));
  expect(screen.getByText("Paused")).toBeVisible();
  expect(screen.getByRole("button", { name: "Resume updates" })).toBeEnabled();
  expect(screen.getByText(/Available guidance.*debugging/)).toBeVisible();
  expect(screen.queryByText("Publisher check in progress…")).toBeNull();
});

it("reports empty task history and publisher checks and shows the first-use action", async () => {
  api.hubRequest.mockResolvedValue({
    ...populated,
    last_task: null,
    last_checked: null,
    job: null,
    projects: [{ ...populated.projects[0], active: [] }],
  });
  const { container } = render(<ToolsHubPanel nativeRuntime />);
  expect(await screen.findByText("No task activity recorded")).toBeVisible();
  expect(screen.getByText("No successful check recorded")).toBeVisible();
  expect(screen.getByText("No guidance installed")).toBeVisible();
  expect(container.querySelector("time")).toBeNull();
  expect(
    screen.getByText(/To start, review and trust Temper/),
  ).toHaveTextContent(
    "To start, review and trust Temper with /hooks in Codex, then open a new chat.",
  );
});

it("shows the first-use action on the configured Overview before the first task", async () => {
  api.hubRequest.mockResolvedValue({
    ...populated,
    last_task: null,
    projects: [{ ...populated.projects[0], active: [] }],
  });
  render(<ToolsHubPanel nativeRuntime onOpenTools={() => {}} />);
  expect(
    await screen.findByText(/To start, review and trust Temper/),
  ).toBeVisible();
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
      screen.getByRole("heading", { name: "Automatic workflows" }),
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
  if (opener !== "Connect Codex") {
    await user.click(await screen.findByText("Tool settings"));
  }
  const trigger = await screen.findByRole("button", {
    name: opener,
  });
  await user.click(trigger);
  await screen.findByRole("dialog", { name: title });
  await user.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("makes every connection preview block reachable before keyboard consent", async () => {
  const user = userEvent.setup();
  api.hubRequest.mockImplementation(async (operation: string) => {
    if (operation === "status")
      return { ...initial, enabled: true, indexed: true };
    return {
      preview_id: "fictional-connection",
      files: [
        {
          path: "C:\\fixture\\config.toml",
          block: "Fictional endpoint settings",
        },
        {
          path: "C:\\fixture\\AGENTS.md",
          block: "Fictional instructions\n".repeat(60),
        },
      ],
    };
  });
  render(<ToolsHubPanel nativeRuntime />);
  await user.click(
    await screen.findByRole("button", { name: "Connect Codex" }),
  );
  const settings = await screen.findByRole("region", {
    name: "Proposed config.toml section",
  });
  expect(
    screen.getByText(/automatically prepare tasks, select tools, render/),
  ).toHaveTextContent(/separately approved runtime/);
  const instructions = screen.getByRole("region", {
    name: "Proposed AGENTS.md section",
  });
  await waitFor(() => expect(settings).toHaveFocus());
  await user.tab();
  expect(instructions).toHaveFocus();
  await user.tab();
  expect(
    screen.getByRole("button", { name: "Allow and continue" }),
  ).toHaveFocus();
  await user.tab();
  expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  await user.tab();
  expect(settings).toHaveFocus();
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

it("serializes status reads and discards a poll superseded by a user action", async () => {
  vi.useFakeTimers();
  const enabled = { ...initial, enabled: true, indexed: true };
  let release: ((value: HubState) => void) | undefined;
  api.hubRequest
    .mockResolvedValueOnce(enabled)
    .mockImplementationOnce(
      () =>
        new Promise<HubState>((resolve) => {
          release = resolve;
        }),
    )
    .mockResolvedValueOnce({ ...enabled, digest: "fresh-digest" })
    .mockResolvedValueOnce({ status: "paused" })
    .mockResolvedValue({ ...enabled, paused: true });
  render(<ToolsHubPanel nativeRuntime />);
  await act(async () => {});
  fireEvent.click(screen.getByText("Tool settings"));

  await act(async () => vi.advanceTimersByTimeAsync(12000));
  expect(api.hubRequest).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Connect Codex" })).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "Pause updates" }));
  expect(api.hubRequest).toHaveBeenCalledTimes(2);
  await act(async () => release?.(initial));

  expect(api.hubRequest).toHaveBeenCalledWith(
    "control",
    { operation: "pause" },
    "fresh-digest",
  );
  expect(screen.getByRole("button", { name: "Resume updates" })).toBeVisible();
  expect(screen.queryByText("Setup available")).toBeNull();
});

it("retains visible repositories on refresh failure and disables changes until recovery", async () => {
  vi.useFakeTimers();
  const enabled = {
    ...initial,
    enabled: true,
    indexed: true,
    native_hooks_configured: true,
    projects: [
      {
        id: "repo",
        label: "Example",
        root: "/example",
        paused: false,
        active: ["debugging"],
        pending_recovery: false,
      },
    ],
  };
  api.hubRequest
    .mockResolvedValueOnce(enabled)
    .mockRejectedValueOnce(new Error("Connection lost"))
    .mockResolvedValue({
      ...enabled,
      projects: [{ ...enabled.projects[0], active: [] }],
    });
  render(<ToolsHubPanel nativeRuntime />);
  expect(screen.getByText("Checking workflow status…")).toBeVisible();
  await act(async () => {});
  expect(screen.getByText(/Available guidance.*debugging/)).toBeVisible();

  await act(async () => vi.advanceTimersByTimeAsync(3000));
  expect(screen.getByText("Status out of date")).toBeVisible();
  expect(screen.getByText("Connection lost")).not.toBeVisible();
  fireEvent.click(screen.getByText("Technical details"));
  expect(screen.getByText("Connection lost")).toBeVisible();
  expect(screen.getByText(/Last known guidance.*debugging/)).toBeVisible();
  expect(screen.queryByText(/Available guidance.*debugging/)).toBeNull();
  fireEvent.click(screen.getByText("Tool settings"));
  expect(screen.getByRole("button", { name: "Pause updates" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
  await act(async () => {});
  expect(screen.getByText("No guidance installed")).toBeVisible();
  expect(screen.queryByText(/Available guidance.*debugging/)).toBeNull();
  expect(screen.getByRole("button", { name: "Pause updates" })).toBeEnabled();
});

it("pauses refresh while the document is hidden and checks status on return", async () => {
  vi.useFakeTimers();
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  api.hubRequest.mockResolvedValue(initial);
  render(<ToolsHubPanel nativeRuntime />);
  await act(async () => {});
  expect(api.hubRequest).toHaveBeenCalledTimes(1);

  hidden.mockReturnValue(true);
  fireEvent(document, new Event("visibilitychange"));
  await act(async () => vi.advanceTimersByTimeAsync(12000));
  expect(api.hubRequest).toHaveBeenCalledTimes(1);
  expect(
    screen.getByRole("button", { name: "Set up repository tools" }),
  ).toBeVisible();

  hidden.mockReturnValue(false);
  fireEvent(document, new Event("visibilitychange"));
  await act(async () => {});
  expect(api.hubRequest).toHaveBeenCalledTimes(2);
});

it("keeps the loaded panel across navigation and refreshes when reopened", async () => {
  vi.useFakeTimers();
  api.hubRequest.mockResolvedValue(initial);
  const panel = (visible: boolean) => (
    <PageVisibility.Provider value={visible}>
      <ToolsHubPanel nativeRuntime />
    </PageVisibility.Provider>
  );
  const { rerender } = render(panel(true));
  await act(async () => {});
  expect(
    screen.getByRole("button", { name: "Set up repository tools" }),
  ).toBeVisible();

  rerender(panel(false));
  await act(async () => vi.advanceTimersByTimeAsync(6000));
  expect(api.hubRequest).toHaveBeenCalledTimes(1);

  rerender(panel(true));
  expect(
    screen.getByRole("button", { name: "Set up repository tools" }),
  ).toBeVisible();
  expect(screen.queryByText("Checking workflow status…")).toBeNull();
  await act(async () => {});
  expect(api.hubRequest).toHaveBeenCalledTimes(2);
});

it("keeps a deferred connection review on Tools and restores it on return", async () => {
  const user = userEvent.setup();
  let resolvePreview: ((value: object) => void) | undefined;
  api.hubRequest.mockImplementation(async (operation: string) => {
    if (operation === "status")
      return { ...initial, enabled: true, indexed: true };
    if (operation === "connection_preview")
      return new Promise((resolve) => {
        resolvePreview = resolve;
      });
    return {};
  });
  const pages = (visible: boolean) => (
    <>
      <button type="button">Next page action</button>
      <div hidden={!visible} inert={!visible}>
        <PageVisibility.Provider value={visible}>
          <ToolsHubPanel nativeRuntime />
        </PageVisibility.Provider>
      </div>
    </>
  );
  const { rerender } = render(pages(true));
  const heading = screen.getByRole("heading", { name: "Automatic workflows" });
  const trigger = await screen.findByRole("button", { name: "Connect Codex" });
  await user.click(trigger);
  await waitFor(() => expect(resolvePreview).toBeDefined());
  rerender(pages(false));
  const nextAction = screen.getByRole("button", { name: "Next page action" });
  nextAction.focus();
  await act(async () => {
    resolvePreview?.({
      preview_id: "fixture-connection",
      files: [{ path: "/fixture/config.toml", block: "Fictional settings" }],
    });
  });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(nextAction).toHaveFocus();

  rerender(pages(true));
  await screen.findByRole("dialog", {
    name: "Connect Codex to repository setup",
  });
  const settings = screen.getByRole("region", {
    name: "Proposed config.toml section",
  });
  await waitFor(() => expect(settings).toHaveFocus());
  expect(settings).toHaveTextContent("Fictional settings");

  const triggerFocus = vi.spyOn(trigger, "focus");
  const headingFocus = vi.spyOn(heading, "focus");
  rerender(pages(false));
  await act(async () => {
    nextAction.focus();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(nextAction).toHaveFocus();
  expect(triggerFocus).not.toHaveBeenCalled();
  expect(headingFocus).not.toHaveBeenCalled();
  expect(
    api.hubRequest.mock.calls.filter(
      ([operation]) => operation === "connection_preview",
    ),
  ).toHaveLength(1);
});

it("explains what to do when the repository picker is empty", async () => {
  const user = userEvent.setup();
  api.hubRequest.mockImplementation(async (operation: string) =>
    operation === "inventory" ? { projects: [] } : initial,
  );
  render(<ToolsHubPanel nativeRuntime />);
  await user.click(
    await screen.findByRole("button", { name: "Set up repository tools" }),
  );
  expect(
    screen.getByText("Add a repository in Temper to continue."),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Review setup" })).toBeDisabled();
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
  await user.click(await screen.findByText("Tool settings"));
  await user.click(screen.getByRole("button", { name: "Pause updates" }));
  await waitFor(() =>
    expect(
      api.hubRequest.mock.calls.filter((call) => call[0] === "status").length,
    ).toBeGreaterThanOrEqual(3),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Permission changed in another window",
  );
});

it("requires separate approval for the exact Windows Remotion toolchain", async () => {
  const user = userEvent.setup();
  let enabled = false;
  let previewFailed = false;
  const paths = {
    node: "C:/fixture/node.exe",
    node_modules: "C:/fixture/node_modules",
    browser: "C:/fixture/chrome-headless-shell.exe",
  };
  api.hubRequest.mockImplementation(async (operation: string) => {
    if (operation === "status")
      return {
        ...initial,
        enabled: true,
        indexed: true,
        remotion_available: true,
        remotion_enabled: enabled,
      };
    if (operation === "runtime_preview") {
      if (!previewFailed) {
        previewFailed = true;
        throw new Error("Private fixture path details");
      }
      return {
        preview_id: "fictional-remotion",
        paths: Object.values(paths),
        projects: ["fixture-repo"],
        admission: {
          version: "4.0.542",
          node_digest: "fixture-node-digest",
          module_tree_digest: "fixture-modules-digest",
          browser_tree_digest: "fixture-browser-digest",
        },
      };
    }
    if (operation === "runtime_enable") enabled = true;
    if (operation === "runtime_revoke") enabled = false;
    return {};
  });
  render(<ToolsHubPanel nativeRuntime />);
  await user.click(await screen.findByText("Tool settings"));
  await user.click(screen.getByText("Remotion video rendering"));
  expect(
    screen.getByText(/full Windows paths to Node.js 24/),
  ).toHaveTextContent(/Remotion 4\.0\.542/);
  const review = screen.getByRole("button", { name: "Review Remotion setup" });
  expect(review).toBeDisabled();
  await user.type(
    screen.getByRole("textbox", { name: "Node executable" }),
    paths.node,
  );
  await user.type(
    screen.getByRole("textbox", { name: "Remotion node_modules directory" }),
    paths.node_modules,
  );
  await user.type(
    screen.getByRole("textbox", { name: "Chrome Headless Shell executable" }),
    paths.browser,
  );
  await user.click(review);
  const error = await screen.findByRole("alert");
  expect(error).toHaveTextContent(/Verify all three paths and versions/);
  expect(error.parentElement).toBe(review.parentElement);
  expect(error).not.toHaveTextContent("Private fixture path details");
  expect(screen.getByRole("textbox", { name: "Node executable" })).toHaveValue(
    paths.node,
  );
  await user.click(review);
  await screen.findByRole("dialog", { name: "Allow Remotion video rendering" });
  expect(screen.getByText(paths.browser)).toBeVisible();
  expect(screen.getByText("fixture-browser-digest")).toBeVisible();
  expect(api.hubRequest).toHaveBeenCalledWith(
    "runtime_preview",
    paths,
    initial.digest,
  );
  expect(
    api.hubRequest.mock.calls.some(
      ([operation]) => operation === "runtime_enable",
    ),
  ).toBe(false);
  await user.click(screen.getByRole("button", { name: "Allow and continue" }));
  const disable = await screen.findByRole("button", {
    name: "Disable Remotion",
  });
  expect(api.hubRequest).toHaveBeenCalledWith(
    "runtime_enable",
    { preview_id: "fictional-remotion" },
    initial.digest,
  );
  disable.focus();
  await user.keyboard("{Enter}");
  await screen.findByRole("button", { name: "Review Remotion setup" });
  expect(screen.getByText("Remotion video rendering")).toHaveFocus();
  await user.tab();
  expect(
    screen.getByRole("textbox", { name: "Node executable" }),
  ).toHaveFocus();
  expect(api.hubRequest).toHaveBeenCalledWith(
    "runtime_revoke",
    {},
    initial.digest,
  );
});

it("hides Remotion admission on unsupported native platforms", async () => {
  api.hubRequest.mockResolvedValue({
    ...initial,
    enabled: true,
    indexed: true,
    remotion_available: false,
  });
  render(<ToolsHubPanel nativeRuntime />);
  await screen.findByText("Tool settings");
  expect(screen.queryByText("Remotion video rendering")).toBeNull();
});
