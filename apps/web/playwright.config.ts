import { defineConfig, devices } from "@playwright/test";

const apiOrigin = "http://127.0.0.1:8010";
const workbenchOrigin = "http://127.0.0.1:3010";
const localApiCommand = [
  "cd ../..",
  "make bootstrap",
  "set -a",
  ". ./.env",
  "set +a",
  ".venv/bin/python -m uvicorn lmpc.server.main:app --host 127.0.0.1 --port 8010",
].join(" && ");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["line"], ["html", { open: "never" }]],
  use: {
    baseURL: workbenchOrigin,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{
    name: "chromium",
    use: { ...devices["Desktop Chrome"] },
  }],
  webServer: [
    {
      name: "LMPC API",
      command: process.env.LMPC_E2E_API_COMMAND || localApiCommand,
      url: `${apiOrigin}/readyz`,
      reuseExistingServer: false,
      timeout: 120_000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
    {
      name: "LMPC Workbench",
      command: "npm run dev -- --hostname 127.0.0.1 --port 3010",
      url: `${workbenchOrigin}/login`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { ...process.env, LMPC_API_ORIGIN: apiOrigin },
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
  ],
});
