import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentBrandMark } from "./AgentBrandMark";

describe("AgentBrandMark", () => {
  it.each([
    ["codex", "openai"],
    ["claude", "claude"],
  ] as const)("renders the %s provider mark decoratively", (agent, brand) => {
    const { container } = render(<AgentBrandMark agent={agent} />);
    const mark = container.querySelector("svg");
    expect(mark).toHaveAttribute("data-agent-brand", brand);
    expect(mark).toHaveAttribute("viewBox", "0 0 24 24");
    expect(mark).toHaveAttribute("aria-hidden", "true");
    expect(mark).toHaveAttribute("focusable", "false");
    expect(
      mark?.querySelector("path")?.getAttribute("d")?.length,
    ).toBeGreaterThan(200);
  });
});
