import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

function componentFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return componentFiles(path);
    return entry.name.endsWith(".tsx") ? [path] : [];
  });
}

describe("renderer visual contracts", () => {
  it("uses Temper controls instead of native select elements", () => {
    const sourceFiles = [
      join(process.cwd(), "src", "App.tsx"),
      ...componentFiles(join(process.cwd(), "src", "components")),
    ];
    for (const path of sourceFiles) {
      expect(readFileSync(path, "utf8"), path).not.toMatch(/<select\b/);
    }
  });

  it("uses provider marks instead of generic robot glyphs for agent connections", () => {
    const pages = readFileSync(
      join(process.cwd(), "src", "components", "pages.tsx"),
      "utf8",
    );
    expect(pages).toContain("<AgentBrandMark agent={connection.id}");
    expect(pages).not.toMatch(/<Bot\b/);
  });

  it("keeps primary navigation motion bounded and reduced-motion aware", () => {
    const styles = readFileSync(
      join(process.cwd(), "src", "styles.css"),
      "utf8",
    );
    expect(styles).toContain("@keyframes screen-enter-forward");
    expect(styles).toContain("@keyframes screen-enter-backward");
    expect(styles).toContain("transform: translate3d(18px, 0, 0)");
    expect(styles).toContain("transform: translate3d(-18px, 0, 0)");
    expect(styles).toMatch(
      /\.screen-transition\[data-direction="forward"\]\s*\{[^}]*260ms/s,
    );
    expect(styles).toMatch(
      /\.screen-transition\[data-direction="backward"\]\s*\{[^}]*260ms/s,
    );
    expect(styles).toContain("@media (prefers-reduced-motion: reduce)");
  });
});
