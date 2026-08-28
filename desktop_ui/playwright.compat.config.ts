import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: /compatibility\.spec\.ts/,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["line"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    locale: "en-US",
    timezoneId: "America/New_York",
  },
  projects: [
    {
      name: "windows-webview2",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "macos-wkwebview",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  webServer: {
    command: "node ./node_modules/vite/bin/vite.js",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
