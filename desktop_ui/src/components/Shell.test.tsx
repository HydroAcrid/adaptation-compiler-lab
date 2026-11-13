import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { loadAutonomy } from "../autonomy";
import { usePageNavigation } from "../usePageNavigation";
import { LearningRepositories } from "./LearningRepositories";
import { NativeStartup } from "./NativeStartup";
import { Shell } from "./Shell";

vi.mock("../autonomy", () => ({
  learningAccessLabel: () => "Learning on",
  loadAutonomy: vi.fn(),
}));

afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

function NavigationFixture() {
  const { screen, setScreen, scrollHost } = usePageNavigation("today");
  return (
    <Shell
      advancedMode={false}
      onNavigate={setScreen}
      pages={{
        today: <h1>Overview page</h1>,
        core: (
          <label>
            Behavior filter
            <input />
          </label>
        ),
        modes: <h1>Tools page</h1>,
        connections: <LearningRepositories />,
        settings: <h1>Settings page</h1>,
        advanced: null,
      }}
      screen={screen}
      scrollHost={scrollHost}
    />
  );
}

it("keeps the workspace navigation visible while opening and retrying", () => {
  const retry = vi.fn();
  const { rerender } = render(
    <NativeStartup advancedMode failure={null} onRetry={retry} />,
  );
  const navigation = screen.getByRole("navigation", { name: "Primary" });
  const main = screen.getByRole("main", { name: "Overview" });

  expect(within(navigation).getAllByRole("button")).toHaveLength(6);
  expect(
    within(navigation).getByRole("button", { name: "Overview" }),
  ).toHaveAttribute("aria-current", "page");
  expect(
    within(navigation).getByRole("button", { name: "Advanced" }),
  ).toBeDisabled();
  expect(within(main).getByRole("status")).toHaveTextContent(
    "Loading your projects and preferences",
  );

  rerender(
    <NativeStartup
      advancedMode
      failure={{ code: "engine_unavailable", message: "Engine unavailable." }}
      onRetry={retry}
    />,
  );
  expect(screen.getByRole("navigation", { name: "Primary" })).toBe(navigation);
  expect(within(main).getByRole("alert")).toHaveTextContent(
    "Engine unavailable.",
  );
  fireEvent.click(within(main).getByRole("button", { name: "Try again" }));
  expect(retry).toHaveBeenCalledOnce();
});

it("mounts pages when opened and preserves their inputs and scroll positions", () => {
  const { container } = render(<NavigationFixture />);
  const main = screen.getByRole("main", { name: "Overview" });
  const overview = screen.getByRole("button", { name: "Overview" });
  const personalization = screen.getByRole("button", {
    name: "Personalization",
  });
  const tools = screen.getByRole("button", { name: "Tools & workflows" });

  expect(container.querySelectorAll(".page-view")).toHaveLength(1);
  expect(loadAutonomy).not.toHaveBeenCalled();
  main.scrollTop = 144;
  fireEvent.click(personalization);
  expect(personalization).toHaveAttribute("aria-current", "page");
  expect(main).toHaveAccessibleName("Personalization");
  expect(main).toHaveFocus();
  expect(main.scrollTop).toBe(0);

  const filter = screen.getByRole("textbox", { name: "Behavior filter" });
  fireEvent.change(filter, { target: { value: "writing" } });
  main.scrollTop = 80;
  fireEvent.click(tools);
  fireEvent.click(overview);
  expect(overview).toHaveAttribute("aria-current", "page");
  expect(main).toHaveFocus();
  expect(main.scrollTop).toBe(144);
  expect(screen.queryByRole("textbox", { name: "Behavior filter" })).toBeNull();
  expect(filter.closest(".page-view")).toHaveAttribute("inert");
  expect(filter.closest(".page-view")).toHaveAttribute("hidden");

  fireEvent.click(personalization);
  expect(screen.getByRole("textbox", { name: "Behavior filter" })).toBe(filter);
  expect(filter).toHaveValue("writing");
  expect(main.scrollTop).toBe(80);
});

it("suspends polling on hidden pages and refreshes once on return", async () => {
  vi.useFakeTimers();
  vi.mocked(loadAutonomy).mockRejectedValue(new Error("Unavailable"));
  render(<NavigationFixture />);

  const connections = screen.getByRole("button", { name: "Connections" });
  const overview = screen.getByRole("button", { name: "Overview" });
  fireEvent.click(connections);
  await act(async () => {});
  expect(loadAutonomy).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert")).toBeVisible();

  fireEvent.click(overview);
  await act(() => vi.advanceTimersByTimeAsync(60_000));
  expect(loadAutonomy).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("alert")).toBeNull();

  fireEvent.click(connections);
  expect(screen.getByRole("alert")).toBeVisible();
  expect(loadAutonomy).toHaveBeenCalledTimes(2);
  await act(() => vi.advanceTimersByTimeAsync(30_000));
  expect(loadAutonomy).toHaveBeenCalledTimes(3);
});
