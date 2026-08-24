import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import App from "./App";

afterEach(() => {
  window.history.replaceState({}, "", "/");
});

describe("Temper prototype", () => {
  it("keeps the everyday Today surface calm and raw-free", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Temper is active in Kairn." }),
    ).toBeInTheDocument();
    expect(screen.getByText(/3 suggestions are ready/i)).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("heading", { name: "Temper is active in Kairn." }),
    ).toBeInTheDocument();
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
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Current project" }),
      "Green Meadow",
    );
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
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Current project" }),
      "Green Meadow",
    );
    expect(
      screen.getByRole("heading", {
        name: "Temper is active in Green Meadow.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Kairn-only knowledge stays out/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Core" }));
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Show for" }),
      "Green Meadow",
    );
    expect(screen.getByText("Green Meadow release shell")).toBeInTheDocument();
    expect(screen.queryByText("Kairn notes can lag")).not.toBeInTheDocument();
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
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Use in" }),
      "Kairn",
    );
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
    expect(within(scope).getAllByRole("option")).toHaveLength(1);
    expect(within(scope).getByRole("option", { name: "Kairn" })).toBeVisible();
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

  it("keeps telemetry off and previews the exact bounded report", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Settings" }));
    expect(
      screen.getByRole("switch", { name: "Help improve Temper" }),
    ).not.toBeChecked();
    await user.click(
      screen.getByRole("button", { name: "Preview exact report" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Exact report preview" }),
    ).toBeInTheDocument();
    expect(screen.getByText("False activations")).toBeInTheDocument();
    expect(
      screen.getByText(/There are no prompts, paths, project names/i),
    ).toBeInTheDocument();
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
      "Connect your coding agents.",
      "Choose where Temper is active.",
      "Temper is ready.",
    ]) {
      await user.click(screen.getByRole("button", { name: "Continue" }));
      expect(
        screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    }
    expect(
      screen.getByRole("switch", { name: "Help improve Temper" }),
    ).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Open Temper" }));
    expect(
      screen.getByRole("heading", { name: "Temper is active in Kairn." }),
    ).toBeInTheDocument();
  });
});
