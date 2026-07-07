import type {
  AssetClass,
  BacktestResult,
  BondAnalytics,
  BookView,
  Construction,
  CreateOrderRequest,
  CreateRfqRequest,
  CreateStrategyRequest,
  CryptoPosition,
  DeskRiskSummary,
  DeskSummary,
  EquityStatus,
  ExecutionQuality,
  Findings,
  ModifyStrategyRequest,
  MicroSnapshot,
  Order,
  PaperOrder,
  PaperOrderRequest,
  Position,
  ProductQuote,
  Rfq,
  RfqExecution,
  Security,
  SecurityVolume,
  SignalMeta,
  StrategyView,
  TaxReport,
  TaxRequest,
  TradePrint,
  YieldCurve,
  ApiError,
} from './types';

// In dev, requests go to /api and Vite proxies them to the backend. In a built
// deployment, VITE_API_BASE can point at the API gateway.
const BASE = (import.meta.env.VITE_API_BASE ?? '') + '/api';
// The risk microservice is exposed under /risk by the dev proxy and nginx.
const RISK_BASE = (import.meta.env.VITE_API_BASE ?? '') + '/risk';
// The Python research service (FastAPI) is exposed under /research.
const RESEARCH_BASE = (import.meta.env.VITE_API_BASE ?? '') + '/research';

/** Error carrying the parsed {@link ApiError} body so callers can show field errors. */
export class HttpError extends Error {
  constructor(public readonly status: number, public readonly body: ApiError | null) {
    super(body?.message ?? `Request failed with status ${status}`);
    this.name = 'HttpError';
  }
}

async function request<T>(path: string, init?: RequestInit, base: string = BASE): Promise<T> {
  const res = await fetch(base + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let body: ApiError | null = null;
    try {
      body = (await res.json()) as ApiError;
    } catch {
      /* non-JSON error body */
    }
    throw new HttpError(res.status, body);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  securities: (assetClass?: AssetClass) =>
    request<Security[]>(`/securities${assetClass ? `?assetClass=${assetClass}` : ''}`),

  // Fixed-income OTC desk (dealer RFQ), the benchmark curve, and bond analytics.
  rfqCreate: (req: CreateRfqRequest) =>
    request<Rfq>('/rfq', { method: 'POST', body: JSON.stringify(req) }),
  rfqList: () => request<Rfq[]>('/rfq'),
  rfqGet: (id: string) => request<Rfq>(`/rfq/${encodeURIComponent(id)}`),
  rfqAccept: (id: string, dealer?: string) =>
    request<RfqExecution>(
      `/rfq/${encodeURIComponent(id)}/accept${dealer ? `?dealer=${encodeURIComponent(dealer)}` : ''}`,
      { method: 'POST' },
    ),
  yieldCurve: () => request<YieldCurve>('/rfq/curve'),
  bondAnalytics: (cusip: string) =>
    request<BondAnalytics>(`/securities/${encodeURIComponent(cusip)}/analytics`),

  // Tax engine (lot accounting, wash sales, §475(f) MTM).
  taxCompute: (req: TaxRequest) =>
    request<TaxReport>('/tax', { method: 'POST', body: JSON.stringify(req) }),

  orders: () => request<Order[]>('/orders'),

  createOrder: (req: CreateOrderRequest) =>
    request<Order>('/orders', { method: 'POST', body: JSON.stringify(req) }),

  stage: (ref: string) => request<Order>(`/orders/${ref}/stage`, { method: 'POST' }),

  route: (ref: string) => request<Order>(`/orders/${ref}/route`, { method: 'POST' }),

  cancel: (ref: string, reason?: string) =>
    request<Order>(`/orders/${ref}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason ?? 'Cancelled from blotter' }),
    }),

  positions: (portfolio: string) =>
    request<Position[]>(`/portfolios/${encodeURIComponent(portfolio)}/positions`),

  // Served by the risk microservice (via the /risk proxy), not the OMS backend.
  riskSummary: () => request<DeskRiskSummary>('/summary', undefined, RISK_BASE),

  // Reporting layer (raw SQL on the backend).
  deskSummary: () => request<DeskSummary>('/analytics/desk-summary'),
  executionQuality: () => request<ExecutionQuality[]>('/analytics/execution-quality'),
  topSecurities: (limit = 6) => request<SecurityVolume[]>(`/analytics/top-securities?limit=${limit}`),

  // Live crypto market (real Coinbase feed + paper trading).
  marketProducts: () => request<ProductQuote[]>('/market/products'),
  marketBook: (product: string, depth = 12) =>
    request<BookView>(`/market/${encodeURIComponent(product)}/book?depth=${depth}`),
  marketTrades: (product: string) =>
    request<TradePrint[]>(`/market/${encodeURIComponent(product)}/trades`),
  marketMicrostructure: (product: string) =>
    request<MicroSnapshot[]>(`/market/${encodeURIComponent(product)}/microstructure`),
  submitPaperOrder: (product: string, req: PaperOrderRequest) =>
    request<PaperOrder>(`/market/${encodeURIComponent(product)}/orders`, {
      method: 'POST',
      body: JSON.stringify(req),
    }),
  cryptoPositions: () => request<CryptoPosition[]>('/market/positions'),
  cryptoOrders: () => request<PaperOrder[]>('/market/orders'),

  // Strategy engine (execution algos + market making) + live controls.
  strategies: () => request<StrategyView[]>('/strategies'),
  createStrategy: (req: CreateStrategyRequest) =>
    request<StrategyView>('/strategies', { method: 'POST', body: JSON.stringify(req) }),
  stopStrategy: (id: string) => request<StrategyView>(`/strategies/${id}/stop`, { method: 'POST' }),
  pauseStrategy: (id: string) => request<StrategyView>(`/strategies/${id}/pause`, { method: 'POST' }),
  resumeStrategy: (id: string) => request<StrategyView>(`/strategies/${id}/resume`, { method: 'POST' }),
  modifyStrategy: (id: string, req: ModifyStrategyRequest) =>
    request<StrategyView>(`/strategies/${id}/modify`, { method: 'POST', body: JSON.stringify(req) }),

  // Equity operational loop (read-only ops status; always available).
  equityStatus: () => request<EquityStatus>('/equity/status'),

  // Research service (Python/FastAPI over the mds research layer).
  researchHealth: () =>
    request<{ status: string; snapshot: boolean; signals: number }>('/health', undefined, RESEARCH_BASE),
  researchSignals: () => request<SignalMeta[]>('/signals', undefined, RESEARCH_BASE),
  researchBacktest: (signal: string, costBps: number, neutralize: boolean) =>
    request<BacktestResult>(
      `/backtest?signal=${encodeURIComponent(signal)}&cost_bps=${costBps}&neutralize=${neutralize}`,
      undefined,
      RESEARCH_BASE,
    ),
  researchFindings: () => request<Findings>('/findings', undefined, RESEARCH_BASE),
  researchConstruction: () => request<Construction>('/construction', undefined, RESEARCH_BASE),
};
