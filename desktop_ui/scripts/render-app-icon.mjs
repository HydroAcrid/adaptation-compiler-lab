import { mkdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = await readFile(
  resolve(root, "public/assets/brand/temper-wind.svg"),
  "utf8",
);
const output = resolve(root, "src-tauri/icons/icon.png");
await mkdir(dirname(output), { recursive: true });

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 512, height: 512 } });
  await page.setContent(`
    <style>
      html, body { margin: 0; width: 512px; height: 512px; background: transparent; }
      body { display: grid; place-items: center; color: #d98955; }
      svg { width: 430px; height: 430px; }
      path { fill: currentColor; }
    </style>
    ${source}
  `);
  await page.locator("svg").screenshot({
    animations: "disabled",
    omitBackground: true,
    path: output,
  });
} finally {
  await browser.close();
}
