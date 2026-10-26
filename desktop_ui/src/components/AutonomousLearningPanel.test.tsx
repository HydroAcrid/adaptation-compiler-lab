import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AutonomousLearningPanel } from "./AutonomousLearningPanel";
import type { AutonomyState } from "../autonomy";
import type { EngineProject } from "../engine";

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
      name: "Synthetic project · synthetic-project",
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
      name: "Synthetic project · synthetic-project",
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
  expect(
    await screen.findByRole("heading", { name: "No habits yet" }),
  ).toBeVisible();
  expect(
    screen.getByText("No habits added to agent instructions"),
  ).toBeVisible();
  expect(screen.queryByText("Personalizing")).not.toBeInTheDocument();
  expect(screen.queryByText("Recent changes")).not.toBeInTheDocument();
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

it("shows signed repository coverage and the prospective cutoff without claiming capture or delivery", async () => {
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
  await screen.findByLabelText("Learning coverage");
  expect(screen.getByText("57")).toBeInTheDocument();
  expect(
    screen.getByText("Conversations captured").nextElementSibling,
  ).toHaveTextContent("0");
  expect(
    screen.getByText(/chats already open at that time stay excluded/),
  ).toBeInTheDocument();
  expect(screen.getByText("No habits yet")).toBeInTheDocument();
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
    screen.queryByText("Add a project in Connections first."),
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
