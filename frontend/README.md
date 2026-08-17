# Trader UI (React 18 · TypeScript · Vite)

The front end: a landing hub linking three self-contained apps — the **exchange & market maker**, the
**fixed-income / OMS desk**, and the **quant research** view — over REST + WebSocket.

## Structure (`src/`)

| Path | What |
|---|---|
| `components/` | Views (Blotter, OrderTicket, Overview, book/market/rates panels). |
| `hooks/` | Data hooks — REST polling (`usePolling`) and live WebSocket streams (`useExchangeStream`, `useMarketStream`, `useRatesStream`), which store the socket in a ref and close it on unmount. |
| `api/` | Typed API client and shared types. |
| `styles.css` | Theme-aware styles; interactive cards use real buttons + focus states (accessibility). |

## Run / test

```bash
npm ci
npm run dev        # Vite dev server (proxies /api and /ws to the backend)
npm test           # Vitest + React Testing Library
npm run build      # typecheck + production build
npm run test:e2e   # Playwright (needs the full stack up)
```
