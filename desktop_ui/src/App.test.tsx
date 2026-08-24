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
      screen.getByRole("heading", { name: "You're all set." }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Temper is quietly working in Kairn."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/sha256/i)).not.toBeInTheDocument();
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
    expect(
      screen.getByRole("heading", { name: "Adaptations" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Adaptation kept for Kairn only",
    );
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
