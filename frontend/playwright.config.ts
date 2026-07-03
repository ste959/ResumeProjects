import { defineConfig } from '@playwright/test';

// End-to-end tests run against a running stack (default: the Docker UI on :8088).
// Override with PLAYWRIGHT_BASE_URL, e.g. http://localhost:5173 for the dev server.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'line' : 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:8088',
    trace: 'on-first-retry',
  },
});
