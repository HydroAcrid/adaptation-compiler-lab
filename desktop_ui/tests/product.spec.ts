import { expect, test } from "@playwright/test";

const supportedWindowSizes = [
  { width: 720, height: 540 },
  { width: 880, height: 640 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2540, height: 1379 },
];

test("primary pages use flat sections instead of cards in both themes", async ({
  page,
}) => {
  const groups = [
    ".tools-hub-panel",
    ".today-review-summary",
    ".autonomy-panel",
    ".learning-facts > div",
    ".personalization-library",
    ".core-group",
    ".native-context",
    ".mode-catalog",
    ".mode-row",
    ".connection-list",
    ".connection-card",
    ".project-list",
    ".project-row",
    ".settings-group",
    ".settings-surface",
    ".toggle-row",
    ".setting-inline",
    ".privacy-summary",
  ].join(", ");
  for (const theme of ["light", "dark"]) {
    for (const screen of [
      "today",
      "core",
      "modes",
      "connections",
      "settings",
    ]) {
      await page.goto(`/?screen=${screen}&theme=${theme}`);
      await expect(page.locator(".page-view--active")).toBeVisible();
      const shapes = await page
        .locator(".page-view--active")
        .locator(groups)
        .evaluateAll((elements) =>
          elements
            .filter(
              (element) =>
                element.getBoundingClientRect().width > 200 &&
                element.getBoundingClientRect().height > 30,
            )
            .map((element) => {
              const style = getComputedStyle(element);
              return {
                selector: element.className,
                shadow: style.boxShadow,
                radius: style.borderTopLeftRadius,
                leftBorder: parseFloat(style.borderLeftWidth),
                rightBorder: parseFloat(style.borderRightWidth),
                background: style.backgroundColor,
              };
            }),
        );
      expect(
        shapes.length,
        `${screen} should exercise real content sections`,
      ).toBeGreaterThan(0);
      for (const shape of shapes) {
        expect(
          shape.shadow,
          `${theme}/${screen}/${shape.selector}: no card shadow`,
        ).toBe("none");
        expect(
          shape.radius,
          `${theme}/${screen}/${shape.selector}: no card corners`,
        ).toBe("0px");
        expect(
          shape.leftBorder + shape.rightBorder,
          `${theme}/${screen}/${shape.selector}: use section rules, not boxed panels`,
        ).toBe(0);
        expect(
          shape.background,
          `${theme}/${screen}/${shape.selector}: no filled card surface`,
        ).toMatch(/^(transparent|rgba\(0, 0, 0, 0\))$/);
      }
    }
  }
});

test("Overview makes automatic workflows visible before learning details", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?screen=today&theme=light");
  const workflows = page.getByRole("region", {
    name: "Automatic workflows",
    exact: true,
  });
  await expect(workflows).toBeVisible();
  await expect(
    workflows.getByText("Codex picks up to two guides for the task."),
  ).not.toBeVisible();
  const heading = await workflows
    .getByRole("heading", { name: "Automatic workflows", exact: true })
    .boundingBox();
  expect(heading?.y).toBeLessThan(300);
  await page.setViewportSize({ width: 720, height: 540 });
  const lifecycle = await workflows
    .getByRole("button", { name: /automatic workflows/i })
    .boundingBox();
  expect(
    lifecycle,
    "Workflow action remains visible at the minimum desktop window",
  ).not.toBeNull();
  expect(
    lifecycle!.y + lifecycle!.height,
    "The workflow action fits in the first viewport",
  ).toBeLessThanOrEqual(540);
  await workflows.getByRole("button", { name: /automatic workflows/i }).click();
  await expect(page.getByRole("main")).toHaveAccessibleName(
    "Tools & workflows",
  );
});

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
    await expect(
      page.getByRole("button", { name: "Overview" }),
    ).toHaveAttribute("aria-current", "page");
  }
});

test("navigation keeps one page visible and restores scroll without transient overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 880, height: 540 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/?screen=today&theme=dark");

  const main = page.getByRole("main");
  const settings = page.getByRole("button", { name: "Settings" });
  await settings.click();
  await expect(main).toHaveAccessibleName("Settings");
  await expect(main).toBeFocused();
  const savedScroll = await main.evaluate((element) => {
    element.scrollTop = 140;
    return element.scrollTop;
  });
  expect(savedScroll).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Connections" }).click();
  await page.getByRole("button", { name: "Overview" }).click();
  await expect(main).toHaveAccessibleName("Overview");
  await expect(page.locator(".page-view:visible")).toHaveCount(1);
  await expect(
    page.locator('.page-view[data-screen="settings"]'),
  ).toHaveAttribute("inert", "");

  const scrollSamples = await main.evaluate(async (element) => {
    const samples: boolean[] = [];
    for (let frame = 0; frame < 12; frame += 1) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      samples.push(element.scrollHeight > element.clientHeight);
    }
    return samples;
  });
  expect(new Set(scrollSamples).size).toBe(1);
  await settings.click();
  await expect(settings).toHaveAttribute("aria-current", "page");
  await expect(main).toBeFocused();
  expect(await main.evaluate((element) => element.scrollTop)).toBe(savedScroll);
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
  await page.getByText("Back up or share preferences", { exact: true }).click();
  await page.getByRole("button", { name: "Import personal backup" }).click();
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
    dialog.getByRole("button", { name: "Add to review" }),
  ).toBeDisabled();
});

test("Frontend Studio is visibly temporary and browser-safe", async ({
  page,
}) => {
  await page.goto("/?screen=modes&theme=dark");
  await page.getByText(/^Saved workflows(?: · \d+)?$/).click();
  await page
    .getByRole("article")
    .filter({ hasText: "Frontend Studio" })
    .getByRole("button", { name: "View workflow" })
    .click();

  const dialog = page.getByRole("dialog", { name: "Frontend Studio" });
  await expect(dialog).toBeVisible();
  await dialog.getByText("Workflow details and sources", { exact: true }).click();
  await expect(dialog.getByText(/one task, up to/i)).toBeVisible();
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
    await expect(
      page.getByRole("button", { name, exact: true }),
    ).toBeDisabled();
  }
  await expect(page.getByText("Sample state")).toBeVisible();
});
