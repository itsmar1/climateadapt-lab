import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Vitest does not use globals, so Testing Library cannot auto-register
// cleanup; do it explicitly (documented RTL + Vitest setup).
afterEach(() => {
  cleanup();
});
