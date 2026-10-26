import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests drive the real app: Django backend + Vite frontend + the configured AI provider.
 * They call the real provider API (small prompts), so a provider key must be set in backend/.env.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 45_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:5173', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1360, height: 860 } }, grepInvert: /@mobile/ },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, grep: /@mobile/ },
  ],
  webServer: [
    {
      // E2E registers many users from one IP, so the auth rate limit is raised for the test server only.
      command: 'THROTTLE_AUTH=200/min DEFAULT_MODEL=${E2E_MODEL:-gemini-3.5-flash-lite} uv run uvicorn config.asgi:application --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/api/health/',
      reuseExistingServer: false,
    },
    { command: 'npx vite --port 5173 --strictPort', url: 'http://localhost:5173', reuseExistingServer: true },
  ],
})
