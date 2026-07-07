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
      // Risk service on :8081 under /risk-api (distinct from the /risk SPA route).
      // /risk-api/summary -> http://localhost:8081/api/risk/summary
      '/risk-api': {
        target: process.env.VITE_RISK_TARGET ?? 'http://localhost:8081',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/risk-api/, '/api/risk'),
      },
      // Research service on :8082 under /research-api (distinct from the /research SPA route).
      // /research-api/backtest -> http://localhost:8082/api/research/backtest
      '/research-api': {
        target: process.env.VITE_RESEARCH_TARGET ?? 'http://localhost:8082',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/research-api/, '/api/research'),
      },
      // Live market-data WebSocket → backend :8080 (ws: true upgrades the connection).
      '/ws': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8080',
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
