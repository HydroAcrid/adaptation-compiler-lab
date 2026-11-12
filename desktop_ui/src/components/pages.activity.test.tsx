import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ConnectionsPage, CorePage, ModesPage, TodayPage } from "./pages";

vi.mock("./AutonomousLearningPanel", () => ({
  AutonomousLearningPanel: () => null,
}));
vi.mock("./LearningRepositories", () => ({ LearningRepositories: () => null }));
vi.mock("./ToolsHubPanel", () => ({ ToolsHubPanel: () => null }));

afterEach(cleanup);

const reviewSummary = {
  activeAdaptationCount: 0,
  health: "ready",
  feedbackAvailable: true,
  pendingFeedbackCount: 1,
  pendingReviewCount: 1,
  projectCount: 1,
  secureStoreReady: true,
} as const;

function overview(health: "ready" | "consent_expired") {
  return (
    <TodayPage
      automaticLearning={false}
      feedback={null}
      liveSummary={{ ...reviewSummary, health }}
      nativeAutonomy
      onFeedback={vi.fn()}
      onOpenCore={vi.fn()}
      onOpenTools={vi.fn()}
      onReview={vi.fn()}
      selectedSuggestionId={null}
      suggestions={[
        {
          automationDisposition: "review-required",
          automationReason: "Needs review",
          behavior: "Summarize the result",
          capturedAt: "2026-01-01T00:00:00Z",
          confidenceReason: "Fixture",
          digest: "fixture",
          explanation: "Make the outcome easier to scan.",
          id: "summary",
          sourceProject: "Fixture project",
          suggestedScope: "Fixture project",
        },
      ]}
      workspace="all"
    />
  );
}

it("shows both review queues and surfaces expired permission in the overview", () => {
  const { rerender } = render(overview("ready"));
  expect(screen.getByText("1 to review · 1 to rate")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Review suggestion" }),
  ).toBeEnabled();
  rerender(overview("consent_expired"));
  expect(
    screen.getByText("Permission expired", { selector: "span" }),
  ).toBeVisible();
  expect(screen.getByText(/Renew permission in Settings/)).toBeVisible();
});

it("shows saved guidance counts while retaining portability actions", async () => {
  const user = userEvent.setup();
  render(
    <CorePage
      initialItems={[
        {
          description: "Include a focused test result.",
          id: "test-result",
          kind: "preference",
          scope: "Everywhere",
          sourceSummary: "Approved suggestion",
          title: "Report test results",
        },
      ]}
    />,
  );
  expect(screen.getByText("1 saved")).toBeVisible();
  expect(screen.getByText("Report test results")).toBeVisible();
  expect(screen.getByRole("button", { name: "Export" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Share pack" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Skills" }));
  expect(screen.getByText("0 saved")).toBeVisible();
  expect(screen.getByText("No items match these filters.")).toBeVisible();
});

it("puts the saved workflow lifecycle explanation behind a disclosure", async () => {
  const user = userEvent.setup();
  render(
    <ModesPage
      error={null}
      loading={false}
      modes={[]}
      nativeRuntime={false}
      onOpenCore={vi.fn()}
      onTaskComplete={vi.fn()}
      projects={[]}
      runnerReady={false}
      snapshotDigest={null}
    />,
  );
  expect(screen.getByText("No saved workflows yet.")).toBeVisible();
  const explanation = screen.getByText(
    "Saved workflows apply to one task at a time.",
  );
  expect(explanation).not.toBeVisible();
  await user.click(screen.getByText("How saved workflows run"));
  expect(explanation).toBeVisible();
});

it("distinguishes unavailable task project data from an empty registry", () => {
  const { rerender } = render(<ConnectionsPage nativeRuntime />);
  expect(screen.getByText("Task agent status unavailable.")).toBeVisible();
  const projects = within(
    screen.getByRole("region", { name: "Task projects" }),
  );
  expect(projects.getByText("Task project status unavailable.")).toBeVisible();
  rerender(<ConnectionsPage nativeRuntime snapshotDigest="fixture" />);
  expect(projects.getByText("No task projects yet.")).toBeVisible();
  expect(
    projects.getByRole("button", { name: "Add task project" }),
  ).toBeEnabled();
});
