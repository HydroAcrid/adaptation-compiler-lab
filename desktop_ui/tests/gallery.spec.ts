import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const screens = [
  "onboarding",
  "today",
  "suggestion",
  "adaptations",
  "connections",
  "settings",
  "advanced",
  "tray",
] as const;

async function openScene(page: Page, screen: string, theme: "light" | "dark") {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/?screen=${screen}&theme=${theme}`);
  await page.locator("body").waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
}

for (const theme of ["light", "dark"] as const) {
  for (const screen of screens) {
    test(`${screen} ${theme} visual`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await openScene(page, screen, theme);
      await expect(page).toHaveScreenshot(`${screen}-1280x800-${theme}.png`, {
        fullPage: true,
      });
      const results = await new AxeBuilder({ page }).analyze();
      if (results.violations.length > 0) {
        console.log(
          JSON.stringify(
            results.violations.map((violation) => ({
              id: violation.id,
              targets: violation.nodes.map((node) => node.target.join(" ")),
            })),
          ),
        );
      }
      expect(results.violations).toEqual([]);
    });
  }
}

for (const viewport of [
  { width: 760, height: 560 },
  { width: 1440, height: 900 },
]) {
  for (const theme of ["light", "dark"] as const) {
    test(`today ${viewport.width}x${viewport.height} ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport);
      await openScene(page, "today", theme);
      await expect(page).toHaveScreenshot(
        `today-${viewport.width}x${viewport.height}-${theme}.png`,
        { fullPage: true },
      );
    });
  }
}
