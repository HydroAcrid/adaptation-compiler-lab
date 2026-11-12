import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { PageVisibility } from "../pageVisibility";
import { ConnectionsPage } from "./pages";
import { LearningRepositories } from "./LearningRepositories";

const api = vi.hoisted(() => ({ loadAutonomy: vi.fn() }));
vi.mock("../autonomy", async (original) => ({
  ...(await original<object>()),
  ...api,
}));
const projects = Array.from({ length: 57 }, (_, index) => ({
  project_id: `learning-${index}`,
  display_name: "Same repository name",
  learning_authorized: index !== 56,
  learning_state: index === 56 ? "off" : index === 55 ? "paused" : "on",
  personalization_enabled: index !== 56,
}));
const response = {
  value: {
    project_access: projects,
    automatic_serving_ready: true,
    secure_store_ready: true,
  },
  digest: `sha256:${"a".repeat(64)}`,
};
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.useRealTimers();
});

it("shows signed learning coverage independently of one task project and absent instruction scans", async () => {
  api.loadAutonomy.mockResolvedValue(response);
  const user = userEvent.setup();
  render(
    <ConnectionsPage
      nativeRuntime
      liveConnections={[
        {
          connection_version: "1.1.0",
          agent_id: "codex",
          display_name: "Codex",
          installation_state: "installed",
          authentication_state: "signed_in",
          conformance_state: "update_required",
          integration_state: "available",
          version_label: "fictional-version",
          status_summary: "The task connection needs an update.",
          learning_capability:
            "Learning is unavailable until the connection is ready.",
          delivery_capability: "Task delivery is unavailable.",
          cost_posture: "No provider call",
          available_actions: ["refresh"],
          raw_payloads_exposed: false,
        },
      ]}
      liveProjects={[
        {
          project_id: "legacy-only",
          display_name: "Legacy task project",
          registered_prospectively: true,
          task_runner_enabled: false,
        },
      ]}
      registrationAvailable={false}
      registrationUnavailableReason="Reviewed-task permission expired."
    />,
  );
  expect(
    await screen.findByText("56 of 57 repositories approved for learning."),
  ).toBeInTheDocument();
  const list = screen.getByLabelText("Learning repositories");
  expect(within(list).getAllByText("Same repository name")).toHaveLength(57);
  expect(within(list).getAllByText("Learning on")).toHaveLength(55);
  expect(within(list).getByText("Learning paused")).toBeInTheDocument();
  expect(within(list).getByText("Learning not approved")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Task connections" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(
      "Learning is unavailable until the connection is ready.",
    ),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(
      "Reviewed-suggestion capture is unavailable until the connection is ready.",
    ),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "View details" }));
  const details = screen.getByRole("dialog");
  expect(
    within(details).getByText(
      "Reviewed-suggestion capture is unavailable until the connection is ready.",
    ),
  ).toBeInTheDocument();
  expect(within(details).getByText("Reviewed suggestions")).toBeInTheDocument();
  expect(
    within(details).getByText(
      /Ordinary Codex chat learning has separate permissions/,
    ),
  ).toBeInTheDocument();
  await user.keyboard("{Escape}");
  const tasks = screen.getByRole("region", { name: "Task projects" });
  expect(within(tasks).getByText("Task runner off")).toBeInTheDocument();
  expect(
    within(tasks).getByText("Agent instructions not checked"),
  ).toBeInTheDocument();
  expect(
    within(tasks).queryByText("No supported agent instructions detected"),
  ).not.toBeInTheDocument();
  expect(
    within(tasks).getByRole("button", { name: "Add task project" }),
  ).toBeDisabled();
  await user.type(
    screen.getByRole("searchbox", { name: "Find a learning repository" }),
    "learning-56",
  );
  expect(within(list).getAllByText("Same repository name")).toHaveLength(1);
  expect(within(list).queryByText("Learning on")).not.toBeInTheDocument();
});

it("marks previous access stale after a failed refresh rather than reporting repositories disabled", async () => {
  api.loadAutonomy
    .mockResolvedValueOnce(response)
    .mockRejectedValueOnce(new Error("Secure store unavailable"));
  const user = userEvent.setup();
  render(<LearningRepositories />);
  await screen.findByText("56 of 57 repositories approved for learning.");
  await user.click(
    screen.getByRole("button", { name: "Refresh learning access" }),
  );
  await screen.findByRole("alert");
  expect(screen.getAllByText("Last known: Learning on")).toHaveLength(55);
  expect(
    screen.queryByText("56 of 57 repositories approved for learning."),
  ).not.toBeInTheDocument();
});

it("queues a manual refresh behind a pending read and ignores superseded permissions", async () => {
  let finishOld!: (value: typeof response) => void;
  let finishFresh!: (value: typeof response) => void;
  api.loadAutonomy
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishOld = resolve;
      }),
    )
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishFresh = resolve;
      }),
    );
  const user = userEvent.setup();
  render(<LearningRepositories />);
  await user.click(
    screen.getByRole("button", { name: "Refresh learning access" }),
  );
  expect(api.loadAutonomy).toHaveBeenCalledTimes(1);
  await act(async () => finishOld(response));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("Same repository name")).not.toBeInTheDocument();

  await act(async () =>
    finishFresh({
      ...response,
      value: { ...response.value, project_access: [] },
    }),
  );
  expect(
    screen.getByText("0 of 0 repositories approved for learning."),
  ).toBeVisible();
});

it("shows enabled personalization waiting when compatibility or storage is unavailable", async () => {
  api.loadAutonomy
    .mockResolvedValueOnce({
      ...response,
      value: { ...response.value, automatic_serving_ready: false },
    })
    .mockResolvedValueOnce({
      ...response,
      value: { ...response.value, secure_store_ready: false },
    });
  const user = userEvent.setup();
  render(<LearningRepositories />);
  await screen.findByText("56 of 57 repositories approved for learning.");
  expect(screen.queryByText("Personalization on")).not.toBeInTheDocument();
  expect(
    screen.getAllByText("Personalization waiting for checks"),
  ).toHaveLength(56);
  await user.click(
    screen.getByRole("button", { name: "Refresh learning access" }),
  );
  await screen.findByText("56 of 57 repositories approved for learning.");
  expect(screen.queryByText("Personalization on")).not.toBeInTheDocument();
});

it("keeps existing rows while refreshing changed permissions on return", async () => {
  let finishRefresh!: (value: typeof response) => void;
  api.loadAutonomy.mockResolvedValueOnce(response).mockReturnValueOnce(
    new Promise((resolve) => {
      finishRefresh = resolve;
    }),
  );
  const repositories = (visible: boolean) => (
    <PageVisibility.Provider value={visible}>
      <LearningRepositories />
    </PageVisibility.Provider>
  );
  const user = userEvent.setup();
  const { rerender } = render(repositories(true));
  await screen.findByText("56 of 57 repositories approved for learning.");
  const query = screen.getByRole("searchbox", {
    name: "Find a learning repository",
  });
  await user.type(query, "learning-0");

  rerender(repositories(false));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(1);
  rerender(repositories(true));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(2);
  expect(query).toHaveValue("learning-0");
  expect(screen.getByText("Learning on")).toBeVisible();

  await act(async () => {
    finishRefresh({
      ...response,
      value: {
        ...response.value,
        project_access: projects.map((project, index) =>
          index === 0 ? { ...project, learning_state: "paused" } : project,
        ),
      },
    });
  });
  expect(screen.getByText("Learning paused")).toBeVisible();
  expect(screen.queryByText("Learning on")).toBeNull();
});

it("queues one fresh read when returning before the previous read finishes", async () => {
  let finishOld!: (value: typeof response) => void;
  api.loadAutonomy
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishOld = resolve;
      }),
    )
    .mockResolvedValueOnce({
      ...response,
      value: { ...response.value, project_access: [] },
    });
  const repositories = (visible: boolean) => (
    <PageVisibility.Provider value={visible}>
      <LearningRepositories />
    </PageVisibility.Provider>
  );
  const { rerender } = render(repositories(true));
  rerender(repositories(false));
  rerender(repositories(true));
  rerender(repositories(false));
  rerender(repositories(true));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(1);
  await act(async () => finishOld(response));

  expect(api.loadAutonomy).toHaveBeenCalledTimes(2);
  expect(
    screen.getByText("0 of 0 repositories approved for learning."),
  ).toBeVisible();
  expect(screen.queryByText("Same repository name")).not.toBeInTheDocument();
});
