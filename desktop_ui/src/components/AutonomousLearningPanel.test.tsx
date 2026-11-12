import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AutonomousLearningPanel } from "./AutonomousLearningPanel";
import type { AutonomyState, Habit } from "../autonomy";
import type { EngineProject } from "../engine";
import { PageVisibility } from "../pageVisibility";

const api = vi.hoisted(() => ({
  loadAutonomy: vi.fn(),
  previewLearningGrant: vi.fn(),
  enableLearningGrant: vi.fn(),
  controlAutonomy: vi.fn(),
  explainHabit: vi.fn(),
}));
vi.mock("../autonomy", () => api);
const digest = `sha256:${"a".repeat(64)}`;
const status: AutonomyState = {
  grant_enabled: false,
  learning_enabled: false,
  personalization_enabled: false,
  automatic_serving_ready: false,
  secure_store_ready: true,
  provenance_state: "unverified",
  capture_state: "paused",
  mode: "shadow",
  published: false,
  delivery_confirmed: false,
  publication_needs_attention: false,
  habits: [],
  recent_changes: [],
  raw_payloads_exposed: false,
};
const project = {
  project_id: "synthetic-project",
  display_name: "Synthetic project",
} as EngineProject;
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
});

it("refreshes externally enabled personalization when the app regains focus", async () => {
  const off = {
    ...status,
    grant_enabled: true,
    learning_enabled: true,
    automatic_serving_ready: true,
    provenance_state: "owner_authorized" as const,
    capture_state: "ready",
  };
  api.loadAutonomy
    .mockResolvedValueOnce({ value: off, digest })
    .mockResolvedValue({
      value: { ...off, personalization_enabled: true },
      digest,
    });
  render(<AutonomousLearningPanel projects={[project]} />);
  await screen.findByText("Off", {
    selector: ".personalization-status strong",
  });
  await act(async () => fireEvent.focus(window));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(2);
  expect(
    screen.getByText("On", { selector: ".personalization-status strong" }),
  ).toBeVisible();
});

it("does not replace a slow status read with overlapping focus or timer reads", async () => {
  const intervals = vi.spyOn(window, "setInterval");
  let finish!: (value: { value: AutonomyState; digest: string }) => void;
  api.loadAutonomy.mockImplementationOnce(
    () => new Promise((resolve) => (finish = resolve)),
  );
  const view = render(<AutonomousLearningPanel projects={[project]} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Checking learning status",
  );
  expect(screen.queryByText("No habits yet.")).not.toBeInTheDocument();
  const tick = intervals.mock.calls[0][0] as () => void;
  await act(async () => {
    fireEvent.focus(window);
    fireEvent(document, new Event("visibilitychange"));
    tick();
  });
  expect(api.loadAutonomy).toHaveBeenCalledTimes(1);
  await act(async () => finish({ value: status, digest }));
  expect(
    screen.getByRole("button", { name: "Review learning access" }),
  ).toBeVisible();
  view.unmount();
  fireEvent.focus(window);
  expect(api.loadAutonomy).toHaveBeenCalledTimes(1);
});

it("refreshes on visibility return and ignores hidden-page events", async () => {
  const visibility = vi.spyOn(document, "visibilityState", "get");
  api.loadAutonomy.mockResolvedValue({ value: status, digest });
  render(<AutonomousLearningPanel projects={[project]} />);
  await screen.findByRole("button", { name: "Review learning access" });
  visibility.mockReturnValue("hidden");
  await act(async () => fireEvent(document, new Event("visibilitychange")));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(1);
  visibility.mockReturnValue("visible");
  await act(async () => fireEvent(document, new Event("visibilitychange")));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(2);
});

it("does not label stale personalization as off when a refresh fails", async () => {
  api.loadAutonomy
    .mockResolvedValueOnce({
      value: {
        ...status,
        grant_enabled: true,
        learning_enabled: true,
        automatic_serving_ready: true,
        provenance_state: "owner_authorized",
        capture_state: "ready",
      },
      digest,
    })
    .mockRejectedValueOnce(new Error("The local engine is unavailable."));
  render(<AutonomousLearningPanel projects={[project]} />);
  await screen.findByText("Off", {
    selector: ".personalization-status strong",
  });
  await act(async () => fireEvent.focus(window));
  expect(
    screen.getByText("Status unavailable", {
      selector: ".personalization-status strong",
    }),
  ).toBeVisible();
  expect(
    screen.queryByText("Off", { selector: ".personalization-status strong" }),
  ).not.toBeInTheDocument();
});

it("makes conversation trust explicit and labels unknown authorship", async () => {
  api.loadAutonomy.mockResolvedValue({ value: status, digest });
  api.previewLearningGrant.mockResolvedValue({
    value: {
      preview_token: "trust-preview",
      native_destination: "/synthetic/AGENTS.md",
      project_ids: [project.project_id],
      categories: ["communication_detail"],
      trust_authorized_chats: true,
      input_authority: "Owner-trusted conversations; authorship unknown.",
      raw_payloads_exposed: false,
    },
    digest,
  });
  const user = userEvent.setup();
  render(<AutonomousLearningPanel projects={[project]} />);
  await screen.findByRole("heading", { name: "Learning" });
  const trust = screen.getByRole("checkbox", {
    name: /Include conversations relayed by agents I authorize/,
  });
  expect(trust).not.toBeChecked();
  await user.click(
    screen.getByRole("checkbox", {
      name: "Synthetic project",
    }),
  );
  await user.click(screen.getByRole("checkbox", { name: "Amount of detail" }));
  await user.click(trust);
  await user.click(
    screen.getByRole("button", { name: "Review learning access" }),
  );
  await screen.findByText(/Agent-relayed conversations are included/);
  expect(api.previewLearningGrant).toHaveBeenCalledWith(
    ["synthetic-project"],
    ["communication_detail"],
    true,
  );
  expect(api.enableLearningGrant).not.toHaveBeenCalled();
});

it("requires selected scope and confirmation before granting permission", async () => {
  api.loadAutonomy.mockResolvedValue({ value: status, digest });
  api.previewLearningGrant.mockResolvedValue({
    value: {
      preview_token: "preview",
      native_destination: "synthetic/AGENTS.md",
      project_ids: [project.project_id],
      categories: ["communication_detail"],
      permission_duration: "until_disabled",
      raw_retention_days: 30,
      effect: "New chats only",
      raw_payloads_exposed: false,
    },
    digest,
  });
  api.enableLearningGrant.mockResolvedValue({
    value: { ...status, grant_enabled: true, learning_enabled: true },
    digest,
  });
  const user = userEvent.setup();
  render(<AutonomousLearningPanel projects={[project]} />);
  await screen.findByRole("button", { name: "Review learning access" });
  expect(
    screen.getByRole("button", { name: "Review learning access" }),
  ).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", {
      name: "Synthetic project",
    }),
  );
  await user.click(screen.getByRole("checkbox", { name: "Amount of detail" }));
  await user.click(
    screen.getByRole("button", { name: "Review learning access" }),
  );
  await screen.findByText(/synthetic\/AGENTS.md/);
  expect(api.enableLearningGrant).not.toHaveBeenCalled();
  expect(api.previewLearningGrant).toHaveBeenCalledWith(
    ["synthetic-project"],
    ["communication_detail"],
    false,
  );
  await user.click(screen.getByRole("button", { name: "Allow learning" }));
  await screen.findByRole("button", { name: "Pause learning" });
  expect(api.enableLearningGrant).toHaveBeenCalledOnce();
  await user.click(screen.getByText("Learning settings"));
  expect(
    screen.getByRole("switch", { name: "Personalization" }),
  ).toBeDisabled();
});

it("binds pause to the current autonomy digest and keeps blocked capture visible", async () => {
  api.loadAutonomy.mockResolvedValue({
    value: { ...status, grant_enabled: true, learning_enabled: true },
    digest,
  });
  api.controlAutonomy.mockResolvedValue({
    value: { ...status, grant_enabled: true },
    digest,
  });
  const user = userEvent.setup();
  render(<AutonomousLearningPanel projects={[project]} />);
  await user.click(
    await screen.findByRole("button", { name: "Pause learning" }),
  );
  await screen.findByRole("button", { name: "Resume learning" });
  expect(api.controlAutonomy).toHaveBeenCalledWith(
    "pause_learning",
    digest,
    undefined,
  );
  expect(
    screen.getByText(/Conversation access needs attention/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/No habits added to agent instructions/),
  ).toBeInTheDocument();
});

it("keeps an empty learning profile distinct from applied personalization", async () => {
  api.loadAutonomy.mockResolvedValue({
    value: {
      ...status,
      grant_enabled: true,
      learning_enabled: true,
      personalization_enabled: true,
      automatic_serving_ready: true,
      provenance_state: "owner_authorized",
      capture_state: "ready",
    },
    digest,
  });
  render(<AutonomousLearningPanel projects={[project]} />);
  expect(await screen.findByText("No habits yet.")).toBeVisible();
  expect(
    screen.getByText("No habits added to agent instructions"),
  ).toBeVisible();
  expect(screen.queryByText("Personalizing")).not.toBeInTheDocument();
  expect(screen.queryByText("Recent changes")).not.toBeInTheDocument();
});

it("leads with scoped habits and shows actual activity while keeping help folded", async () => {
  const habit: Habit = {
    habit_id: "concise-updates",
    behavior: "Give concise progress updates.",
    project_id: project.project_id,
    task_class: "progress_update",
    origin: "inferred",
    state: "active",
    support_episode_ids: ["task-one", "task-two"],
    contradiction_episode_ids: [],
  };
  const current: AutonomyState = {
    ...status,
    grant_enabled: true,
    learning_enabled: true,
    personalization_enabled: true,
    automatic_serving_ready: true,
    provenance_state: "owner_authorized",
    capture_state: "ready",
    published: true,
    habits: [
      habit,
      {
        ...habit,
        habit_id: "removed-habit",
        behavior: "Write a detailed narrative.",
        state: "retired",
      },
    ],
    project_access: [
      {
        project_id: project.project_id,
        display_name: "Approved project",
        learning_authorized: true,
        learning_state: "on",
        personalization_enabled: true,
      },
    ],
    capture_summary: {
      eligible_since: "2026-10-22T14:58:19Z",
      captured_conversations: 8,
      read_at: "2026-11-02T15:00:00Z",
    },
    recent_changes: [
      { type: "habit", digest: "habit-change" },
      { type: "publication", digest: "publication-change" },
    ],
  };
  api.loadAutonomy
    .mockResolvedValueOnce({ value: current, digest })
    .mockRejectedValueOnce(new Error("Read failed"))
    .mockResolvedValue({ value: current, digest });
  api.explainHabit.mockResolvedValue({
    value: {
      habit,
      support_count: 2,
      contradiction_count: 0,
      outcome_summary: {
        habit_revision: 1,
        published: true,
        delivered: null,
        followed: null,
        helpful: null,
        harmful: null,
        checked_opportunities: 0,
      },
    },
    digest,
  });
  api.controlAutonomy.mockResolvedValue({
    value: {
      ...current,
      published: false,
      habits: [{ ...habit, state: "retired" }],
    },
    digest,
  });
  const user = userEvent.setup();
  render(<AutonomousLearningPanel projects={[project]} />);
  const heading = await screen.findByRole("heading", { name: habit.behavior });
  const row = heading.closest("li")!;
  expect(within(row).getByText("Active")).toBeVisible();
  expect(
    within(row).getByText(
      /Approved project · progress update · Learned from chats/,
    ),
  ).toBeVisible();
  expect(
    screen.queryByText("Write a detailed narrative."),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("Conversations captured").nextElementSibling,
  ).toHaveTextContent("8");
  expect(screen.getByText("Agent instructions updated")).toBeVisible();
  expect(screen.getByText(/agent loading unconfirmed/)).toBeVisible();
  expect(screen.getByText("Analysis and storage")).not.toBeVisible();
  await act(async () => fireEvent.focus(window));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "last status could not be refreshed",
  );
  expect(heading).toBeVisible();
  expect(screen.getByLabelText("Last known activity")).toBeVisible();
  expect(screen.getByText("Last known activity")).toBeVisible();
  expect(
    screen.getByText("Last known approved repositories (1)"),
  ).toBeVisible();
  expect(
    within(row).getByRole("button", { name: "Undo habit" }),
  ).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  const explain = await within(row).findByRole("button", {
    name: "Why this habit?",
  });
  expect(explain).toBeEnabled();
  await user.click(explain);
  expect(await screen.findByText(/2 supporting tasks/)).toBeVisible();
  expect(
    screen.getByText("Loaded by an agent").nextElementSibling,
  ).toHaveTextContent("Not measured");
  expect(api.explainHabit).toHaveBeenCalledWith(habit.habit_id);
  await user.click(within(row).getByRole("button", { name: "Undo habit" }));
  expect(await screen.findByText("No habits yet.")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Learned habits" })).toHaveFocus();
  expect(api.controlAutonomy).toHaveBeenCalledWith(
    "revoke_habit",
    digest,
    habit.habit_id,
  );
});

it("cannot replace a successful pause with an older status poll", async () => {
  const intervals = vi.spyOn(window, "setInterval");
  const ready = {
    ...status,
    grant_enabled: true,
    learning_enabled: true,
    provenance_state: "owner_authorized" as const,
    capture_state: "ready",
  };
  let resolveOld!: (value: { value: AutonomyState; digest: string }) => void;
  api.loadAutonomy
    .mockResolvedValueOnce({ value: ready, digest })
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );
  api.controlAutonomy.mockResolvedValue({
    value: { ...ready, learning_enabled: false },
    digest,
  });
  const user = userEvent.setup();
  render(<AutonomousLearningPanel projects={[project]} />);
  await screen.findByRole("button", { name: "Pause learning" });
  const refresh = intervals.mock.calls.find(
    ([, delay]) => delay === 30_000,
  )?.[0];
  if (typeof refresh !== "function")
    throw new Error("Learning polling was not scheduled");
  act(() => refresh());
  await user.click(screen.getByRole("button", { name: "Pause learning" }));
  await screen.findByRole("button", { name: "Resume learning" });
  await act(async () => resolveOld({ value: ready, digest }));
  expect(screen.getByRole("button", { name: "Resume learning" })).toBeEnabled();
  expect(api.controlAutonomy).toHaveBeenCalledWith(
    "pause_learning",
    digest,
    undefined,
  );
});

it("shows a status failure and allows a read-only retry", async () => {
  api.loadAutonomy
    .mockRejectedValueOnce(new Error("Status unavailable"))
    .mockResolvedValueOnce({ value: status, digest });
  const user = userEvent.setup();
  render(<AutonomousLearningPanel projects={[project]} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Learning status is unavailable",
  );
  expect(
    screen.queryByRole("button", { name: "Allow learning" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByRole("button", { name: "Review learning access" });
  expect(api.enableLearningGrant).not.toHaveBeenCalled();
  expect(api.controlAutonomy).not.toHaveBeenCalled();
});

it("shows signed repository coverage and keeps the cutoff in help", async () => {
  api.loadAutonomy.mockResolvedValue({
    value: {
      ...status,
      grant_enabled: true,
      learning_enabled: true,
      personalization_enabled: true,
      automatic_serving_ready: true,
      provenance_state: "owner_authorized",
      capture_state: "ready",
      project_access: Array.from({ length: 57 }, (_, i) => ({
        project_id: `new-${i}`,
        display_name: `New ${i}`,
        learning_authorized: true,
        learning_state: "on",
        personalization_enabled: true,
      })),
      capture_summary: {
        eligible_since: "2026-10-22T14:58:19Z",
        captured_conversations: 0,
        read_at: "2026-10-26T15:00:00Z",
      },
    },
    digest,
  });
  render(<AutonomousLearningPanel projects={[project]} />);
  await screen.findByLabelText("Learning activity");
  expect(screen.getByText("Approved repositories (57)")).toBeVisible();
  expect(
    screen.getByText("Conversations captured").nextElementSibling,
  ).toHaveTextContent("0");
  expect(screen.getByText(/Older chats are excluded/)).not.toBeVisible();
  expect(screen.getByText("No habits yet.")).toBeVisible();
  const user = userEvent.setup();
  await user.click(screen.getByText("Approved repositories (57)"));
  expect(screen.getByText("New 56")).toBeVisible();
  expect(screen.queryByText("Synthetic project")).not.toBeInTheDocument();
  await user.click(screen.getByText("How chat learning works"));
  expect(screen.getByText(/Learning cutoff/)).toBeVisible();
  expect(screen.getByText("Source").nextElementSibling).toHaveTextContent(
    "Older chats are excluded.",
  );
});

it("describes completed work in ongoing chats only when that capture policy is enabled", async () => {
  api.loadAutonomy.mockResolvedValue({
    value: {
      ...status,
      grant_enabled: true,
      learning_enabled: true,
      capture_window: "completed_work",
      capture_state: "ready",
      provenance_state: "owner_authorized",
      capture_summary: {
        eligible_since: "2026-10-22T14:58:19Z",
        captured_conversations: 1,
        read_at: "2026-11-02T15:00:00Z",
      },
    },
    digest,
  });
  render(<AutonomousLearningPanel projects={[project]} />);
  expect(
    await screen.findByText(/including ongoing Codex chats/),
  ).not.toBeVisible();
  await userEvent.setup().click(screen.getByText("How chat learning works"));
  expect(screen.getByText("Source").nextElementSibling).toHaveTextContent(
    "Completed work in approved projects, including ongoing Codex chats. Messages before your learning cutoff are excluded.",
  );
  expect(
    screen.queryByText(/Older chats are excluded/),
  ).not.toBeInTheDocument();
});

it("disambiguates same-name learning repositories when granting permission", async () => {
  api.loadAutonomy.mockResolvedValue({
    value: {
      ...status,
      project_access: ["first", "second"].map((id) => ({
        project_id: id,
        display_name: "Same name",
        learning_authorized: false,
        learning_state: "off",
        personalization_enabled: false,
      })),
    },
    digest,
  });
  api.previewLearningGrant.mockResolvedValue({
    value: {
      preview_token: "duplicate-preview",
      native_destination: "/fictional/AGENTS.md",
      project_ids: ["second"],
      categories: ["communication_detail"],
      raw_payloads_exposed: false,
    },
    digest,
  });
  const user = userEvent.setup();
  render(<AutonomousLearningPanel projects={[]} />);
  await screen.findByRole("checkbox", { name: "Same name · second" });
  expect(
    screen.queryByText("Add a learning project in Connections first."),
  ).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("checkbox", { name: "Same name · second" }),
  );
  await user.click(screen.getByRole("checkbox", { name: "Amount of detail" }));
  await user.click(
    screen.getByRole("button", { name: "Review learning access" }),
  );
  expect(api.previewLearningGrant).toHaveBeenCalledWith(
    ["second"],
    ["communication_detail"],
    false,
  );
  expect(api.enableLearningGrant).not.toHaveBeenCalled();
});

it("shows measured coverage on Overview without claiming the observer is running", async () => {
  const open = vi.fn();
  api.loadAutonomy.mockResolvedValue({
    value: {
      ...status,
      grant_enabled: true,
      learning_enabled: true,
      provenance_state: "owner_authorized",
      capture_state: "ready",
      project_access: [
        {
          project_id: project.project_id,
          display_name: project.display_name,
          learning_authorized: true,
          learning_state: "on",
          personalization_enabled: false,
        },
      ],
    },
    digest,
  });
  render(
    <AutonomousLearningPanel
      projects={[project]}
      onOpenPersonalization={open}
    />,
  );
  expect(await screen.findByText("Enabled")).toBeVisible();
  expect(
    screen.queryByText(/are eligible for learning/),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("Conversations captured").nextElementSibling,
  ).toHaveTextContent("Unavailable");
  expect(
    screen.getByText("Approved projects").nextElementSibling,
  ).toHaveTextContent("1");
  expect(
    screen.queryByRole("button", { name: "Pause learning" }),
  ).not.toBeInTheDocument();
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Manage learning" }));
  expect(open).toHaveBeenCalledOnce();
  api.loadAutonomy.mockRejectedValueOnce(new Error("Read unavailable"));
  await act(async () => fireEvent.focus(window));
  expect(await screen.findByText("Last known learning coverage")).toBeVisible();
  expect(
    screen.getByText("Approved projects").nextElementSibling,
  ).toHaveTextContent("1");
});

it("suspends page status reads while another page is selected", async () => {
  api.loadAutonomy.mockResolvedValue({ value: status, digest });
  const panel = (visible: boolean) => (
    <PageVisibility.Provider value={visible}>
      <AutonomousLearningPanel projects={[project]} />
    </PageVisibility.Provider>
  );
  const view = render(panel(false));
  fireEvent.focus(window);
  expect(api.loadAutonomy).not.toHaveBeenCalled();
  view.rerender(panel(true));
  await screen.findByRole("button", { name: "Review learning access" });
  view.rerender(panel(false));
  fireEvent.focus(window);
  expect(api.loadAutonomy).toHaveBeenCalledOnce();
});

it("serializes a pending read across rapid page switches", async () => {
  let finish!: (value: { value: AutonomyState; digest: string }) => void;
  api.loadAutonomy
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue({ value: status, digest });
  const view = render(
    <PageVisibility value={true}>
      <AutonomousLearningPanel projects={[project]} />
    </PageVisibility>,
  );
  view.rerender(
    <PageVisibility value={false}>
      <AutonomousLearningPanel projects={[project]} />
    </PageVisibility>,
  );
  view.rerender(
    <PageVisibility value={true}>
      <AutonomousLearningPanel projects={[project]} />
    </PageVisibility>,
  );
  expect(api.loadAutonomy).toHaveBeenCalledTimes(1);
  await act(async () => finish({ value: status, digest }));
  expect(api.loadAutonomy).toHaveBeenCalledTimes(2);
  expect(
    screen.getByRole("button", { name: "Review learning access" }),
  ).toBeVisible();
});
