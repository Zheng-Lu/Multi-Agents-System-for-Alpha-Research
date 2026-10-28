import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:8000', headless: true },
  webServer: {
    command: '../.venv/bin/uvicorn alpha_mas.api.app:app --host 127.0.0.1 --port 8000',
    url: 'http://127.0.0.1:8000/api/health',
    reuseExistingServer: !process.env.CI,
    env: { ALPHA_DB: `/tmp/alpha-e2e-${process.pid}.db`, ALPHA_ALLOW_LIVE: 'false' },
  },
});
