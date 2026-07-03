import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Component/unit tests run under jsdom via Vitest. Playwright E2E tests live in e2e/
// and are excluded here (they have their own runner).
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
