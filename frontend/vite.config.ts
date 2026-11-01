import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Dev server port 5173 matches the backend CORS default
// (CLIMATEADAPT_API_CORS_ORIGINS=http://localhost:5173). strictPort fails
// loudly instead of silently moving to a non-allowed origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Playwright specs have their own runner; Vitest must not collect them
    // (its default include matches *.spec.ts).
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    // Headroom for loaded machines: the 5 s default flakes first-in-file
    // tests when workers starve (observed on this box under parallel load).
    testTimeout: 15000,
  },
});
