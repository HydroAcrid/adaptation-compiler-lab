import { render, screen } from "@testing-library/react";
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
    expect(screen.getByRole("button", { name: "Keep" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Only in Kairn" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ignore" })).toBeInTheDocument();
  });

  it("supports a project-only decision and presents a reversible result", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", { name: /review suggestion/i }),
    );
    await user.click(screen.getByRole("button", { name: "Only in Kairn" }));
    expect(screen.getByRole("heading", { name: "Core" })).toBeInTheDocument();
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
});
