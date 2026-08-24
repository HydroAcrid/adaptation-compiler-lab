import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const everydayScreens = [
  "onboarding",
  "today",
  "suggestion",
  "core",
  "connections",
  "settings",
] as const;

async function openMinimumWindow(page: Page, screen: string) {
  await page.setViewportSize({ width: 720, height: 540 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/?screen=${screen}&theme=dark`);
  await page.locator("body").waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
}

for (const screen of everydayScreens) {
  test(`${screen} is accessible and overflow-free at the supported minimum`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const unexpectedRequests: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.hostname !== "127.0.0.1") unexpectedRequests.push(request.url());
    });

    await openMinimumWindow(page, screen);

    const overflow = await page.locator("html").evaluate((element) => ({
      document: element.scrollWidth > element.clientWidth,
      main:
        document.querySelector(".main-content") instanceof HTMLElement
          ? document.querySelector<HTMLElement>(".main-content")!.scrollWidth >
            document.querySelector<HTMLElement>(".main-content")!.clientWidth
          : false,
    }));
    expect(overflow).toEqual({ document: false, main: false });
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(consoleErrors).toEqual([]);
    expect(unexpectedRequests).toEqual([]);
  });
}

test("review decisions preserve or narrow scope", async ({ page }) => {
  await openMinimumWindow(page, "today");
  await page.getByRole("button", { name: /review suggestion/i }).click();
  await expect(
    page.getByRole("button", { name: "Keep as suggested" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Only in Kairn" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Close review" }).click();

  await page
    .getByRole("button", { name: /prefer names that represent real things/i })
    .click();
  await page.getByRole("button", { name: "Only in Kairn" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Adaptation kept for Kairn only",
  );
});

test("project-only Core knowledge cannot be widened", async ({ page }) => {
  await openMinimumWindow(page, "core");
  const item = page
    .getByText("Kairn notes can lag")
    .locator("xpath=ancestor::article");
  await item.getByRole("button", { name: "Edit" }).click();
  const scope = page.getByRole("combobox", { name: "Use in" });
  await expect(scope.getByRole("option")).toHaveCount(1);
  await expect(scope).toHaveValue("Kairn");
});
