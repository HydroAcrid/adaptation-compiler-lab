import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import App from "./App";

afterEach(() => {
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
  document.body.style.removeProperty("pointer-events");
  document.body.removeAttribute("data-scroll-locked");
});

describe("Temper prototype", () => {
  it("keeps the everyday Today surface calm and raw-free", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", {
        name: "3 suggestions to review.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/nothing changes until you decide/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Automatic option available")).toBeInTheDocument();
    expect(screen.queryByText(/sha256/i)).not.toBeInTheDocument();
  });

  it("ranks several suggestions without turning Today into a bulk-review dashboard", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByText("3 ready")).toBeInTheDocument();
    expect(
      screen.getAllByText("Strong evidence").length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Developing evidence")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: /when notes and the repository disagree/i,
      }),
    );
    expect(
      screen.getByRole("dialog", { name: /when notes and the repository/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Your review stays required/i)).toBeInTheDocument();
  });

  it("keeps navigation state aligned with the visible folio", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(document.querySelector(".screen-transition")).toHaveAttribute(
      "data-screen",
      "settings",
    );
    expect(document.querySelector(".screen-transition")).toHaveAttribute(
      "data-direction",
      "forward",
    );
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("heading", {
        name: "3 suggestions to review.",
      }),
    ).toBeInTheDocument();
    expect(document.querySelector(".screen-transition")).toHaveAttribute(
      "data-screen",
      "today",
    );
    expect(document.querySelector(".screen-transition")).toHaveAttribute(
      "data-direction",
      "backward",
    );
  });

  it("shows temporary capability Modes as separate from Core", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Modes" }));

    expect(screen.getByRole("heading", { name: "Modes" })).toBeInTheDocument();
    expect(screen.getByText("Frontend Studio")).toBeInTheDocument();
    expect(screen.getByText("Research Analyst")).toBeInTheDocument();
    expect(screen.getByText("Secure Backend")).toBeInTheDocument();
    expect(screen.getAllByText(/experimental/i)).toHaveLength(3);
    expect(
      screen.getByText(/Core stays yours and stays unchanged/i),
    ).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "View Mode" })[0]!);
    expect(
      screen.getByRole("dialog", { name: "Frontend Studio" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/One exact managed task/i)).toBeInTheDocument();
    expect(
      screen.getByText(/6 conformance checks passed/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/comparison not run yet/i)).toBeInTheDocument();
  });

  it("previews profile portability without pretending browser writes are native", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=core");
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Export" }));
    expect(
      screen.getByRole("dialog", { name: "Take your Core with you" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/private paths are not included/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save encrypted profile" }),
    ).toBeDisabled();
    expect(screen.getByText(/visual browser preview/i)).toBeInTheDocument();
  });

  it("shows that imported profiles remain inactive until review", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=core");
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Import" }));
    await user.type(
      screen.getByLabelText("Profile passphrase"),
      "correct horse battery staple",
    );
    await user.click(
      screen.getByRole("button", { name: "Open example preview" }),
    );
    expect(
      screen.getByText(/remains inactive until you review/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Stage for review" }),
    ).toBeDisabled();
  });

  it("reviews one suggestion without mutating from a notification", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", { name: /review suggestion/i }),
    );
    expect(
      screen.getByRole("dialog", { name: /lead with the purpose/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Keep as suggested" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Only in Kairn" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ignore" })).toBeInTheDocument();
  });

  it("keeps the suggested project scope without widening it", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", { name: /review suggestion/i }),
    );
    await user.click(screen.getByRole("button", { name: "Keep as suggested" }));
    expect(screen.getByRole("heading", { name: "Core" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Adaptation kept for Kairn",
    );
    expect(screen.getByRole("status")).not.toHaveTextContent("all projects");
  });

  it("offers project-only narrowing for a global suggestion", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", {
        name: /prefer names that represent real things/i,
      }),
    );
    await user.click(screen.getByRole("button", { name: "Only in Kairn" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Adaptation kept for Kairn only",
    );
  });

  it("records lightweight usefulness feedback", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", { name: "Workspace: All projects" }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Green Meadow/i }));
    await user.click(screen.getByRole("button", { name: "Helped" }));
    expect(screen.getByText(/Recorded as helped/i)).toBeInTheDocument();
  });

  it("removes and restores an approved Core item", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=core");
    render(<App />);
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(8);
    await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(7);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(8);
  });

  it("switches projects without leaking another project's knowledge", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", { name: "Workspace: All projects" }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Green Meadow/i }));
    expect(
      screen.getByRole("heading", {
        name: "1 suggestion to review.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Prefer names that represent real things/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Suggestion 1 of 1")).toBeInTheDocument();
    expect(
      screen.queryByText(/Lead with the purpose before setup steps/i),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Core" }));
    const scope = screen.getByRole("combobox", { name: "Show for" });
    expect(scope.tagName).toBe("BUTTON");
    expect(document.querySelector("select")).not.toBeInTheDocument();
    await user.click(scope);
    await user.click(screen.getByRole("option", { name: "Green Meadow" }));
    expect(screen.getByText("Green Meadow release shell")).toBeInTheDocument();
    expect(screen.queryByText("Kairn notes can lag")).not.toBeInTheDocument();
  });

  it("shows all project knowledge together and supports a focused Kairn view", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=core");
    render(<App />);
    expect(screen.getByText("Kairn notes can lag")).toBeInTheDocument();
    expect(screen.getByText("Green Meadow release shell")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Workspace: All projects" }),
    );
    await user.click(screen.getByRole("menuitem", { name: /^Kairn/i }));
    expect(screen.getByText("Kairn notes can lag")).toBeInTheDocument();
    expect(
      screen.queryByText("Green Meadow release shell"),
    ).not.toBeInTheDocument();
  });

  it("does not present native connection actions as working in the browser preview", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Connections" }));
    expect(
      document.querySelectorAll('[data-agent-brand="openai"]'),
    ).toHaveLength(1);
    expect(
      document.querySelectorAll('[data-agent-brand="claude"]'),
    ).toHaveLength(1);
    expect(
      screen.getByText(/browser preview cannot change agent accounts/i),
    ).toBeInTheDocument();
    const detailButtons = screen.getAllByRole("button", {
      name: "View details",
    });
    expect(detailButtons).toHaveLength(2);
    await user.click(detailButtons[0]);
    expect(screen.getByRole("dialog", { name: "Codex" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.getByRole("button", { name: "Add project" })).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Manage Kairn" }),
    ).not.toBeInTheDocument();
  });

  it("edits Core wording and scope from a focused sheet", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=core");
    render(<App />);
    await user.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    expect(
      screen.getByRole("dialog", { name: /edit purpose before procedure/i }),
    ).toBeInTheDocument();
    const name = screen.getByRole("textbox", { name: "Name" });
    await user.clear(name);
    await user.type(name, "Purpose, then steps");
    await user.click(screen.getByRole("combobox", { name: "Use in" }));
    await user.click(screen.getByRole("option", { name: "Kairn" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText("Purpose, then steps")).toBeInTheDocument();
    expect(
      screen.getByText(/Kairn · Approved from 3 explicit corrections/i),
    ).toBeInTheDocument();
  });

  it("never offers scope widening for project-only Core items", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=core");
    render(<App />);
    const kairnItem = screen
      .getByText("Kairn notes can lag")
      .closest("article");
    expect(kairnItem).not.toBeNull();
    await user.click(
      within(kairnItem as HTMLElement).getByRole("button", { name: "Edit" }),
    );
    const scope = screen.getByRole("combobox", { name: "Use in" });
    await user.click(scope);
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option", { name: "Kairn" })).toBeVisible();
    await user.keyboard("[Escape]");
  });

  it("blocks empty Core wording", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=core");
    render(<App />);
    await user.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    await user.clear(screen.getByRole("textbox", { name: "Name" }));
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("shows advanced navigation only after explicit opt-in", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(
      screen.queryByRole("button", { name: "Advanced" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("switch", { name: "Advanced mode" }));
    expect(
      screen.getByRole("button", { name: "Advanced" }),
    ).toBeInTheDocument();
  });

  it("keeps narrow automatic learning off until the user enables it", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Settings" }));
    const automaticLearning = screen.getByRole("switch", {
      name: "Automatic low-risk learning",
    });
    expect(automaticLearning).not.toBeChecked();
    expect(
      screen.getByText(/strong, low-impact project preferences/i),
    ).toBeInTheDocument();
    await user.click(automaticLearning);
    expect(automaticLearning).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.getByText("Automatic with 24-hour undo")).toBeInTheDocument();
  });

  it("keeps the document theme and native window color aligned", async () => {
    const user = userEvent.setup();
    const themeColor = document.createElement("meta");
    themeColor.name = "theme-color";
    document.head.append(themeColor);
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute(
      "content",
      "#161412",
    );
    themeColor.remove();
  });

  it("keeps telemetry off and labels browser telemetry as a sample", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(
      screen.getByRole("switch", { name: "Help improve Temper" }),
    ).not.toBeChecked();
    await user.click(
      screen.getByRole("button", { name: "Preview sample report" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Exact report preview" }),
    ).toBeInTheDocument();
    expect(screen.getByText("False activations")).toBeInTheDocument();
    expect(
      screen.getByText(/There are no prompts, paths, project names/i),
    ).toBeInTheDocument();
  });

  it("shows consent without exposing governed internals", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("button", { name: "View consent" }));
    expect(
      screen.getByRole("dialog", { name: "Local consent" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Sample only")).toBeInTheDocument();
    expect(screen.queryByText(/sha256/i)).not.toBeInTheDocument();
  });

  it("does not pretend the browser telemetry sample is a live cloud control", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByText("Browser preview only")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Upload history" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete cloud reports" }),
    ).not.toBeInTheDocument();
  });

  it("supports onboarding without requiring a Temper account", () => {
    window.history.replaceState({}, "", "/?screen=onboarding");
    render(<App />);
    expect(
      screen.getByRole("heading", { name: /your way of working/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Nothing becomes durable until you approve it/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/create account/i)).not.toBeInTheDocument();
  });

  it("completes every onboarding step with telemetry still off", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/?screen=onboarding");
    render(<App />);
    for (const heading of [
      "Local by design.",
      "Check your coding agents.",
      "Register your first project.",
      "Ready to set up Temper.",
    ]) {
      await user.click(screen.getByRole("button", { name: "Continue" }));
      expect(
        screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    }
    expect(
      screen.getByRole("switch", {
        name: "Allow Temper to learn in this project",
      }),
    ).not.toBeChecked();
    expect(screen.getByText(/telemetry.*stay off/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open Temper" }));
    expect(
      screen.getByRole("heading", {
        name: "3 suggestions to review.",
      }),
    ).toBeInTheDocument();
  });
});
