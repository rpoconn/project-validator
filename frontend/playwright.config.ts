import { defineConfig, devices } from '@playwright/test'

// Dedicated ports so the suite never talks to a dev server that's already running.
const API_PORT = 18000
const WEB_PORT = 15173
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`

/**
 * End-to-end tests against the real backend and frontend.
 *
 * The backend runs with `LLM_MOCK=1` (canned reviews from an offline fake of the Messages API, so
 * runs are free and deterministic) and an in-memory database, so every run starts empty. The specs
 * share that database and run in order, which is why parallelism and retries are off.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env['CI'],
  reporter: process.env['CI'] ? 'github' : 'list',
  use: {
    baseURL: WEB_URL,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `uv --directory ../backend run uvicorn src.main:app --host 127.0.0.1 --port ${API_PORT}`,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      env: {
        LLM_MOCK: '1',
        ANTHROPIC_API_KEY: '',
        DATABASE_URL: 'sqlite+aiosqlite://',
        LOG_LEVEL: 'WARNING',
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: WEB_URL,
      env: { VITE_API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
