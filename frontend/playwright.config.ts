import { defineConfig } from '@playwright/test';

// E2E runs the production bundle from file:// (no dev server needed) with the
// backend fully mocked via page.route. Uses the machine's installed Chrome
// (channel: 'chrome', per Playwright browsers docs) so no browser download
// is required. Build first: `npm run build:e2e` (relative asset base).
export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  reporter: 'list',
  use: {
    channel: 'chrome',
    viewport: { width: 1280, height: 900 },
    launchOptions: {
      // The suite serves the bundle from file:// (no dev server); this flag
      // lets the page load its own module/CSS subresources.
      args: ['--allow-file-access-from-files'],
    },
  },
});
