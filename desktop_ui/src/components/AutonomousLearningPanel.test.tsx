import { cleanup, render, screen } from "@testing-library/react";
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
  await screen.findByText(/Capture is blocked/);
  expect(
    screen.getByRole("button", { name: "Preview permission" }),
  ).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: "Synthetic project" }));
  await user.click(screen.getByRole("checkbox", { name: "Amount of detail" }));
  await user.click(screen.getByRole("button", { name: "Preview permission" }));
  await screen.findByText(/synthetic\/AGENTS.md/);
  expect(api.enableLearningGrant).not.toHaveBeenCalled();
  expect(api.previewLearningGrant).toHaveBeenCalledWith(
    ["synthetic-project"],
    ["communication_detail"],
  );
  await user.click(
    screen.getByRole("button", { name: "Confirm scoped permission" }),
  );
  await screen.findByRole("button", { name: "Pause learning" });
  expect(api.enableLearningGrant).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("button", { name: "Enable personalization" }),
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
  expect(screen.getByText(/Capture is blocked/)).toBeInTheDocument();
  expect(
    screen.getByText(/Delivery and usefulness have not been established/),
  ).toBeInTheDocument();
});
