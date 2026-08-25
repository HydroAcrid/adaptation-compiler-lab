import { expect, test } from "@playwright/test";

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
  await page.getByRole("button", { name: "View Mode" }).click();

  const dialog = page.getByRole("dialog", { name: "Frontend Studio" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/one exact managed task/i)).toBeVisible();
  await expect(dialog.getByText(/added tools/i)).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Available in desktop app" }),
  ).toBeDisabled();
});
