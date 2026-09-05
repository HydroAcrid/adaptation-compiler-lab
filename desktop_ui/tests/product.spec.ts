import { expect, test } from "@playwright/test";

const supportedWindowSizes = [
  { width: 720, height: 540 },
  { width: 880, height: 640 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2540, height: 1379 },
];

test("the product surface fills the real window at every supported size", async ({
  page,
}) => {
  await page.goto("/?screen=today&theme=dark");
  await expect(page.locator(".window-dragbar")).toHaveCount(0);

  for (const viewport of supportedWindowSizes) {
    await page.setViewportSize(viewport);
    const shell = await page.locator(".window-shell").boundingBox();
    const layout = await page.locator(".app-layout").boundingBox();
    expect(shell).toEqual({ x: 0, y: 0, ...viewport });
    expect(layout?.x).toBe(0);
    expect(layout?.width).toBe(viewport.width);
    expect(layout?.y).toBeGreaterThan(0);
    expect((layout?.y ?? 0) + (layout?.height ?? 0)).toBe(viewport.height);
    await expect(
      page.getByText(/browser preview · sample data/i),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Today" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  }
});

test("primary navigation follows tab order without transient vertical overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/?screen=today&theme=dark");

  async function sampleVerticalOverflow() {
    return page.locator(".main-content").evaluate(async (element) => {
      const samples: boolean[] = [];
      for (let frame = 0; frame < 18; frame += 1) {
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => resolve()),
        );
        samples.push(element.scrollHeight > element.clientHeight);
      }
      return samples;
    });
  }

  await page.getByRole("button", { name: "Connections" }).click();
  const forwardPage = page.locator(
    '.screen-transition[data-screen="connections"]',
  );
  await expect(forwardPage).toHaveAttribute("data-direction", "forward");
  expect(
    await forwardPage.evaluate(
      (element) => getComputedStyle(element).animationName,
    ),
  ).toBe("screen-enter-forward");
  expect(new Set(await sampleVerticalOverflow()).size).toBe(1);

  await page.getByRole("button", { name: "Today" }).click();
  const backwardPage = page.locator('.screen-transition[data-screen="today"]');
  await expect(backwardPage).toHaveAttribute("data-direction", "backward");
  expect(
    await backwardPage.evaluate(
      (element) => getComputedStyle(element).animationName,
    ),
  ).toBe("screen-enter-backward");
  expect(new Set(await sampleVerticalOverflow()).size).toBe(1);
});

test("onboarding fills the real window instead of rendering a mock window", async ({
  page,
}) => {
  await page.setViewportSize({ width: 880, height: 640 });
  await page.goto("/?screen=onboarding&theme=dark");
  const onboarding = await page.locator(".onboarding-shell").boundingBox();
  expect(onboarding).toEqual({ x: 0, y: 0, width: 880, height: 640 });
  await expect(page.locator(".window-dragbar")).toHaveCount(0);
  await expect(
    page.getByRole("complementary", { name: "Browser preview notice" }),
  ).toContainText("sample data");
});

test("profile import preview remains visible and inactive", async ({
  page,
}) => {
  await page.goto("/?screen=core&theme=dark");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page
    .getByLabel("Profile passphrase")
    .fill("correct horse battery staple");
  await page.getByRole("button", { name: "Open example preview" }).click();

  const dialog = page.getByRole("dialog", { name: "Review a Temper profile" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByText(/remains inactive until you review/i),
  ).toBeVisible();
  await expect(
    dialog.getByText(/does not become your instruction authority/i),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Stage for review" }),
  ).toBeDisabled();
});

test("Frontend Studio is visibly temporary and browser-safe", async ({
  page,
}) => {
  await page.goto("/?screen=modes&theme=dark");
  await page
    .getByRole("article")
    .filter({ hasText: "Frontend Studio" })
    .getByRole("button", { name: "View Mode" })
    .click();

  const dialog = page.getByRole("dialog", { name: "Frontend Studio" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/one exact managed task/i)).toBeVisible();
  await expect(dialog.getByText(/added tools/i)).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Available in desktop app" }),
  ).toBeDisabled();
});

test("the browser connection example is neutral about absent Claude", async ({
  page,
}) => {
  await page.goto("/?screen=connections&theme=dark");

  const claude = page.getByRole("article").filter({ hasText: "Claude Code" });
  await expect(
    claude.getByText("Not installed", { exact: true }),
  ).toBeVisible();
  await expect(
    claude.getByText("Needs attention", { exact: true }),
  ).toHaveCount(0);
});

test("browser-only scenes do not expose inert native actions", async ({
  page,
}) => {
  await page.goto("/?screen=onboarding&theme=dark");
  for (let step = 0; step < 3; step += 1) {
    await page.getByRole("button", { name: "Continue" }).click();
  }
  await expect(
    page.getByRole("button", {
      name: "Project selection is available in the desktop app",
    }),
  ).toBeDisabled();

  await page.goto("/?screen=suggestion&theme=dark");
  await expect(page.getByText(/sample preview · this decision/i)).toBeVisible();

  await page.goto("/?screen=advanced&theme=dark");
  await expect(
    page.getByRole("button", { name: "Available in desktop app" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Apply reviewed changes" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Refresh diagnostics" }),
  ).toBeDisabled();
  await expect(page.getByText("Sample diff", { exact: true })).toBeVisible();

  await page.goto("/?screen=tray&theme=dark");
  for (const name of ["Pause Temper", "Open Temper", "Help", "Quit"]) {
    await expect(page.getByRole("button", { name })).toBeDisabled();
  }
  await expect(page.getByText("Sample state")).toBeVisible();
});
