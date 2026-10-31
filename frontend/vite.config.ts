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
  },
});
