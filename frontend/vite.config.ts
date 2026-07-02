import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server proxies /api to the Spring Boot backend so the browser talks to a
// single origin in development (no CORS surprises).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8080',
        changeOrigin: true,
      },
      // Risk service lives on :8081; expose it under /risk so the browser stays
      // single-origin. /risk/summary -> http://localhost:8081/api/risk/summary
      '/risk': {
        target: process.env.VITE_RISK_TARGET ?? 'http://localhost:8081',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/risk/, '/api/risk'),
      },
    },
  },
});
