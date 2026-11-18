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
      workspaceProjectId={null}
    />
  );
}

it("opens actionable reviews and leaves expired permission behind the disclosure", async () => {
  const user = userEvent.setup();
  const { rerender } = render(overview("ready"));
  expect(screen.getByText("1 to review · 1 to rate")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Review suggestion" }),
  ).toBeEnabled();
  rerender(overview("consent_expired"));
  expect(
    screen.getByText("Permission expired", { selector: "span" }),
  ).toBeVisible();
  const renewal = screen.getByText(/Renew permission under View permissions/);
  expect(renewal).not.toBeVisible();
  await user.click(
    screen.getByText("Reviewed suggestions", { selector: "summary" }),
  );
  expect(renewal).toBeVisible();
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
  expect(
    screen.getByText("Back up or share preferences").closest("details"),
  ).not.toHaveAttribute("open");
  await user.click(screen.getByText("Back up or share preferences"));
  expect(
    screen.getByRole("button", { name: "Export personal backup" }),
  ).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "Import personal backup" }),
  ).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "Share preferences" }),
  ).toBeEnabled();
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
  expect(screen.getByText("No saved workflows yet.")).not.toBeVisible();
  await user.click(screen.getByText("Saved workflows"));
  expect(screen.getByText("No saved workflows yet.")).toBeVisible();
  const explanation = screen.getByText(
    "Saved workflows apply to one task at a time.",
  );
  expect(explanation).not.toBeVisible();
  await user.click(screen.getByText("How saved workflows run"));
  expect(explanation).toBeVisible();
});

it("distinguishes loading, unavailable, and empty managed task project data", async () => {
  const user = userEvent.setup();
  const { rerender } = render(
    <ConnectionsPage nativeRuntime connectionsLoading projectsLoading />,
  );
  await user.click(
    screen.getByRole("button", { name: "Open managed task setup" }),
  );
  expect(
    screen.getByText("Managed task setup", { selector: "summary" }),
  ).toHaveFocus();
  expect(screen.getByText("Checking task agents…")).toBeVisible();
  expect(screen.getByText("Loading task projects…")).toBeVisible();
  expect(screen.queryByText("No task projects yet.")).not.toBeInTheDocument();
  rerender(<ConnectionsPage nativeRuntime />);
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

it("keeps connection rows short and preserves capability and cost details in the dialog", async () => {
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
          conformance_state: "compatible",
          integration_state: "connected",
          version_label: "fixture",
          status_summary: "Ready to use with Temper.",
          learning_capability: "Can capture approved completed tasks.",
          delivery_capability: "Delivers guidance to managed tasks.",
          cost_posture: "Uses the connected subscription.",
          available_actions: ["refresh"],
          raw_payloads_exposed: false,
        },
        {
          connection_version: "1.1.0",
          agent_id: "claude",
          display_name: "Claude Code",
          installation_state: "installed",
          authentication_state: "signed_in",
          conformance_state: "compatible",
          integration_state: "attention",
          version_label: "fixture",
          status_summary: "Review the local hook configuration.",
          learning_capability: "Capture is unavailable.",
          delivery_capability: "Delivery is unavailable.",
          cost_posture: "Agent usage is billed separately.",
          available_actions: ["refresh"],
          raw_payloads_exposed: false,
        },
      ]}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Open managed task setup" }),
  );
  const rows = within(screen.getByRole("region", { name: "Task connections" }));
  expect(rows.getByText("Ready", { exact: true })).toBeVisible();
  expect(rows.getByText("Needs attention", { exact: true })).toBeVisible();
  expect(rows.getByText("Review the local hook configuration.")).toBeVisible();
  expect(rows.queryByText("Ready to use with Temper.")).not.toBeInTheDocument();
  expect(
    rows.queryByText("Can capture approved completed tasks."),
  ).not.toBeInTheDocument();
  expect(
    rows.queryByText("Delivers guidance to managed tasks."),
  ).not.toBeInTheDocument();
  expect(
    rows.queryByText(/Uses the connected subscription/),
  ).not.toBeInTheDocument();

  await user.click(rows.getAllByRole("button", { name: "View details" })[0]!);
  const dialog = within(screen.getByRole("dialog", { name: "Codex" }));
  expect(
    dialog.getByText("Can capture approved completed tasks."),
  ).toBeVisible();
  expect(dialog.getByText("Delivers guidance to managed tasks.")).toBeVisible();
  expect(dialog.getByText(/Uses the connected subscription/)).toBeVisible();
});

it("identifies each feedback target and submits the selected delivery", async () => {
  const user = userEvent.setup();
  const onFeedback = vi.fn();
  render(
    <TodayPage
      automaticLearning={false}
      feedback={null}
      feedbackTargets={[
        {
          id: "east-delivery",
          taskLabel: "Dispatch East",
          completedAt: "2026-10-04T10:00:00Z",
          guidance: ["Release details"],
          outcomes: ["helped", "hurt"],
        },
        {
          id: "west-delivery",
          taskLabel: "Dispatch West",
          completedAt: "2026-10-04T13:00:00Z",
          guidance: ["Brief summaries"],
          outcomes: ["irrelevant"],
        },
      ]}
      liveSummary={{
        ...reviewSummary,
        pendingFeedbackCount: 2,
        pendingReviewCount: 0,
      }}
      nativeAutonomy
      onFeedback={onFeedback}
      onOpenCore={vi.fn()}
      onOpenTools={vi.fn()}
      onReview={vi.fn()}
      selectedSuggestionId={null}
      suggestions={[]}
      workspaceProjectId={null}
    />,
  );

  const east = screen.getByRole("group", {
    name: "Rate guidance for Dispatch East",
  });
  const west = screen.getByRole("group", {
    name: "Rate guidance for Dispatch West",
  });
  expect(screen.getByText("Brief summaries")).toBeVisible();
  expect(screen.getByText("Release details")).toBeVisible();
  expect(document.querySelectorAll("time")).toHaveLength(2);
  expect(within(east).queryByRole("button", { name: "Irrelevant" })).toBeNull();
  await user.click(within(west).getByRole("button", { name: "Irrelevant" }));
  expect(onFeedback).toHaveBeenCalledExactlyOnceWith(
    "irrelevant",
    "west-delivery",
  );
});
