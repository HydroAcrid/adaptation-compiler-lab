import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
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
      liveConnections={[]}
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
  const tasks = screen.getByRole("region", { name: "Managed-task projects" });
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

it("does not let an older refresh overwrite newer repository permissions", async () => {
  let finish!: (value: typeof response) => void;
  api.loadAutonomy
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    )
    .mockResolvedValueOnce({ ...response, value: { project_access: [] } });
  const user = userEvent.setup();
  render(<LearningRepositories />);
  await user.click(
    screen.getByRole("button", { name: "Refresh learning access" }),
  );
  await screen.findByText("0 of 0 repositories approved for learning.");
  await act(async () => finish(response));
  expect(
    screen.getByText("0 of 0 repositories approved for learning."),
  ).toBeInTheDocument();
  expect(screen.queryByText("Same repository name")).not.toBeInTheDocument();
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
