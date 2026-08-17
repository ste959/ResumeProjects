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
  ExAnalytics,
  ExecutionQuality,
  Findings,
  ModifyStrategyRequest,
  MicroSnapshot,
  MicroStudy,
  QpStatus,
  QpPosition,
  QpOrder,
  QpHistory,
  QpEngine,
  LabTemplates,
  LabResult,
  LabPromoteResult,
  Screener,
  Technicals,
  Sector,
  NewsItem,
  Catalysts,
  Order,
  Page,
  PaperOrder,
  PaperOrderRequest,
  PlaceExRequest,
  PlaceExResponse,
  Position,
  RaRfq,
  RatesRfqRequest,
  RatesShockRequest,
  RatesSnapshot,
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
import { getToken, type LoginResponse } from '../auth/session';

// In dev, requests go to /api and Vite proxies them to the backend. In a built
// deployment, VITE_API_BASE can point at the API gateway.
const BASE = (import.meta.env.VITE_API_BASE ?? '') + '/api';
// The risk microservice is proxied under /risk-api (NOT /risk — that is the SPA route for the Risk
// tab; a same-named proxy prefix would shadow it and 301 a browser refresh into the API).
const RISK_BASE = (import.meta.env.VITE_API_BASE ?? '') + '/risk-api';
// The Python research service (FastAPI) under /research-api (likewise distinct from the /research SPA route).
const RESEARCH_BASE = (import.meta.env.VITE_API_BASE ?? '') + '/research-api';

/** Error carrying the parsed {@link ApiError} body so callers can show field errors. */
export class HttpError extends Error {
  constructor(public readonly status: number, public readonly body: ApiError | null) {
    super(body?.message ?? `Request failed with status ${status}`);
    this.name = 'HttpError';
  }
}

async function request<T>(path: string, init?: RequestInit, base: string = BASE): Promise<T> {
  // Attach the signed JWT when present. Reads are public, so a signed-out user still sees data;
  // writes need the header (the backend enforces roles via @PreAuthorize).
  const token = getToken();
  const res = await fetch(base + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
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
  // Authentication (Java OMS). login returns a signed JWT; me echoes the caller's identity.
  login: (username: string, password: string) =>
    request<LoginResponse>('/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

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

  // The blotter is a keyset page; the UI shows the most recent page (cap 200) and unwraps the envelope.
  orders: () => request<Page<Order>>('/orders?size=200').then((p) => p.content),

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

  // Matching engine (place/cancel into our exchange; market data streams over /ws/exchange).
  placeExchangeOrder: (req: PlaceExRequest) =>
    request<PlaceExResponse>('/exchange/orders', { method: 'POST', body: JSON.stringify(req) }),
  cancelExchangeOrder: (id: number) =>
    request<{ orderId: number; cancelled: boolean }>(`/exchange/orders/${id}/cancel`, { method: 'POST' }),
  exchangeAnalytics: () => request<ExAnalytics>('/exchange/analytics'),

  // Rates desk (dealer RFQ + curve shock; market data streams over /ws/rates).
  ratesSnapshot: () => request<RatesSnapshot>('/rates/snapshot'),
  ratesSubmitRfq: (req: RatesRfqRequest) =>
    request<RaRfq>('/rates/rfq', { method: 'POST', body: JSON.stringify(req) }),
  ratesShock: (req: RatesShockRequest) =>
    request<RatesSnapshot>('/rates/shock', { method: 'POST', body: JSON.stringify(req) }),

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
  researchMicrostructure: (ic: number, signal: string) =>
    request<MicroStudy>(
      `/microstructure?ic=${ic}&signal=${encodeURIComponent(signal)}`,
      undefined,
      RESEARCH_BASE,
    ),

  // Quant Desk — Alpaca-backed live paper trading (research → backtest → live).
  qpStatus: () => request<QpStatus>('/status', undefined, RESEARCH_BASE),
  qpPositions: () => request<QpPosition[]>('/live/positions', undefined, RESEARCH_BASE),
  qpOrders: () => request<QpOrder[]>('/live/orders', undefined, RESEARCH_BASE),
  qpHistory: (period = '1M', timeframe = '1D') =>
    request<QpHistory>(`/live/history?period=${period}&timeframe=${timeframe}`, undefined, RESEARCH_BASE),

  // Live strategy engine.
  qpStrategies: () => request<QpEngine>('/strategies', undefined, RESEARCH_BASE),
  qpArm: (id: string) => request<QpEngine>(`/strategies/${id}/arm`, { method: 'POST' }, RESEARCH_BASE),
  qpDisarm: (id: string) => request<QpEngine>(`/strategies/${id}/disarm`, { method: 'POST' }, RESEARCH_BASE),
  qpFlatten: (id: string) => request<QpEngine>(`/strategies/${id}/flatten`, { method: 'POST' }, RESEARCH_BASE),
  qpKill: () => request<QpEngine>('/strategies/kill', { method: 'POST' }, RESEARCH_BASE),
  qpResume: () => request<QpEngine>('/strategies/resume', { method: 'POST' }, RESEARCH_BASE),

  // Backtest lab.
  labTemplates: () => request<LabTemplates>('/lab/templates', undefined, RESEARCH_BASE),
  labBacktest: (q: { kind: string; symbol: string; timeframe: string; cost_bps: number; fast: number; slow: number; lookback: number }) =>
    request<LabResult>(
      `/lab/backtest?kind=${q.kind}&symbol=${encodeURIComponent(q.symbol)}&timeframe=${q.timeframe}` +
        `&cost_bps=${q.cost_bps}&fast=${q.fast}&slow=${q.slow}&lookback=${q.lookback}`,
      undefined,
      RESEARCH_BASE,
    ),
  labWalkforward: (kind: string, symbol: string, timeframe: string, costBps: number) =>
    request<LabResult>(
      `/lab/walkforward?kind=${kind}&symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&cost_bps=${costBps}`,
      undefined, RESEARCH_BASE),
  labPromote: (body: { kind: string; symbol: string; timeframe: string; params: Record<string, number>; notional: number }) =>
    request<LabPromoteResult>('/lab/promote', { method: 'POST', body: JSON.stringify(body) }, RESEARCH_BASE),

  // Exploration.
  mktScreener: () => request<Screener>('/market/screener', undefined, RESEARCH_BASE),
  mktTechnicals: (symbol: string) => request<Technicals>(`/market/technicals?symbol=${encodeURIComponent(symbol)}`, undefined, RESEARCH_BASE),
  mktSectors: () => request<Sector[]>('/market/sectors', undefined, RESEARCH_BASE),
  mktNews: (symbols = '', limit = 20) =>
    request<NewsItem[]>(`/market/news?symbols=${encodeURIComponent(symbols)}&limit=${limit}`, undefined, RESEARCH_BASE),
  mktCatalysts: () => request<Catalysts>('/market/catalysts', undefined, RESEARCH_BASE),
};
