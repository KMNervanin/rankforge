import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: { browserName: 'chromium', headless: true, baseURL: 'http://127.0.0.1:4197', viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: 'node --import tsx tests/e2e-server.ts', url: 'http://127.0.0.1:4197/api/bootstrap', reuseExistingServer: false, timeout: 30000 },
})
