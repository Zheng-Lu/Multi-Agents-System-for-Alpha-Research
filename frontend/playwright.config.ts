import { defineConfig } from '@playwright/test';
const port = Number(process.env.ALPHA_E2E_PORT ?? '8137');
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid ALPHA_E2E_PORT');
const baseURL = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  use: { baseURL, headless: true },
  webServer: {
    command: `../.venv/bin/uvicorn alpha_mas.api.app:app --host 127.0.0.1 --port ${port}`,
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
    env: { ALPHA_DB: `/tmp/alpha-e2e-${process.pid}.db`, ALPHA_ALLOW_LIVE: 'false' },
  },
});
