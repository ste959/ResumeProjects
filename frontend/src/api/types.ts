// Mirrors the backend DTOs. Kept as a single source of truth for the UI's data shapes.

export type OrderSide = 'BUY' | 'SELL';
export type OrderType = 'MARKET' | 'LIMIT';
export type TimeInForce = 'DAY' | 'GTC' | 'IOC' | 'FOK';

export type OrderStatus =
  | 'NEW'
  | 'STAGED'
  | 'ROUTED'
  | 'PARTIALLY_FILLED'
  | 'FILLED'
  | 'CANCELLED'
  | 'REJECTED';

export type AssetClass = 'FIXED_INCOME' | 'EQUITY';

export interface Security {
  cusip: string;
  assetClass?: AssetClass;
  ticker?: string;
  isin: string;
  description: string;
  issuer: string;
  couponRate: number;
  maturityDate: string;
  faceValue: number;
  currency: string;
  sector: string;
  rating: string;
  investmentGrade: boolean;
  cleanPrice: number;
  restricted: boolean;
}

export interface Execution {
  id: number;
  quantity: number;
  price: number;
  venue: string;
  executedAt: string;
}

export interface Order {
  orderRef: string;
  cusip: string;
  securityDescription: string;
  portfolio: string;
  trader: string;
  side: OrderSide;
  orderType: OrderType;
  timeInForce: TimeInForce;
  quantity: number;
  limitPrice: number | null;
  status: OrderStatus;
  filledQuantity: number;
  remainingQuantity: number;
  avgFillPrice: number | null;
  statusReason: string | null;
  createdAt: string;
  updatedAt: string;
  executions: Execution[];
}

export interface Position {
  portfolio: string;
  cusip: string;
  securityDescription: string;
  netQuantity: number;
  avgCost: number;
  markPrice: number;
  marketValue: number;
  updatedAt: string;
}

export interface CreateOrderRequest {
  cusip: string;
  portfolio: string;
  trader: string;
  side: OrderSide;
  orderType: OrderType;
  timeInForce: TimeInForce;
  quantity: number;
  limitPrice?: number | null;
}

export interface DeskSummary {
  totalOrders: number;
  filledOrders: number;
  workingOrders: number;
  rejectedOrders: number;
  totalFilledFace: number;
  fillRatePct: number;
}

export interface ExecutionQuality {
  cusip: string;
  description: string;
  side: OrderSide;
  orderCount: number;
  filledFace: number;
  avgFillPrice: number;
  benchmarkPrice: number;
  slippageBps: number;
}

export interface SecurityVolume {
  cusip: string;
  description: string;
  tradedFace: number;
  fillCount: number;
}

export interface PortfolioRisk {
  portfolio: string;
  orderCount: number;
  workingOrders: number;
  rejectedOrders: number;
  filledFace: number;
}

export interface DeskRiskSummary {
  totalOrders: number;
  totalFilledFace: number;
  ordersByStatus: Record<string, number>;
  portfolios: PortfolioRisk[];
}

// ---- Live crypto market (real Coinbase feed) ----

export interface ProductQuote {
  product: string;
  bestBid: number | null;
  bestAsk: number | null;
  mid: number | null;
  spread: number | null;
  spreadBps: number | null;
  lastPrice: number | null;
}

export interface DepthLevel {
  price: number;
  size: number;
  cumulative: number;
}

export interface BookView {
  product: string;
  quote: ProductQuote;
  bids: DepthLevel[];
  asks: DepthLevel[];
}

export interface TradePrint {
  seq?: number;
  product: string;
  price: number;
  size: number;
  side: string;
  time: string;
}

export interface PaperOrderRequest {
  side: 'BUY' | 'SELL';
  type: 'MARKET' | 'LIMIT';
  size: number;
  limitPrice?: number | null;
}

export interface PaperFill {
  price: number;
  size: number;
}

export interface PaperOrder {
  id: string;
  product: string;
  side: 'BUY' | 'SELL';
  type: 'MARKET' | 'LIMIT';
  requestedSize: number;
  limitPrice: number | null;
  status: string;
  filledSize: number;
  avgPrice: number | null;
  notional: number;
  slippageBps: number;
  createdAt: string;
  fills: PaperFill[];
}

export interface MicroSnapshot {
  epochMillis: number;
  mid: number;
  microprice: number;
  imbalance: number;
  spreadBps: number;
  microPremiumBps: number;
}

export interface CryptoPosition {
  product: string;
  netSize: number;
  avgCost: number;
  markPrice: number | null;
  marketValue: number | null;
  unrealizedPnl: number | null;
}

// ---- Strategy engine (execution algos + market making) ----

export interface StrategyView {
  id: string;
  type: string;
  product: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  position: number;
  avgCost: number;
  markPrice: number;
  realizedPnl: number;
  unrealizedPnl: number;
  totalPnl: number;
  numFills: number;
  parentSide: string | null;
  parentSize: number | null;
  executedSize: number | null;
  avgExecPrice: number | null;
  arrivalMid: number | null;
  implementationShortfallBps: number | null;
  quoteBid: number;
  quoteAsk: number;
}

export interface CreateStrategyRequest {
  type: string;
  product: string;
  side?: string;
  size?: number | null;
  slices?: number | null;
  participation?: number | null;
  kappa?: number | null;
  gamma?: number | null;
  tau?: number | null;
  quoteSize?: number | null;
}

export interface ApiError {
  timestamp: string;
  status: number;
  error: string;
  message: string;
  path: string;
  fieldErrors?: Record<string, string>;
}

// ---- Research service (Python/FastAPI bridge over the mds research layer) ----

export interface SignalMeta {
  name: string;
  family: string;
  label: string;
  desc: string;
}

export interface EquityPoint {
  date: string;
  value: number;
}

export interface BacktestResult {
  signal: string;
  label: string;
  family: string;
  cost_bps: number;
  neutralized: boolean;
  net_sharpe: number | null;
  gross_sharpe: number | null;
  hac_t: number | null;
  boot_lo: number | null;
  boot_hi: number | null;
  ann_return: number | null;
  max_drawdown: number | null;
  avg_turnover: number | null;
  days: number;
  bonferroni_z: number | null;
  significant: boolean;
  equity_curve: EquityPoint[];
  verdict: string;
}

export interface FindingRow {
  name: string;
  label: string;
  family: string;
  net_sharpe: number | null;
  hac_t: number | null;
  turnover: number | null;
  significant: boolean;
}

export interface Findings {
  universe: { names: number; days: number; start: string; end: string };
  signals: FindingRow[];
  selection: {
    best: string;
    best_label: string;
    deflated_sharpe: number | null;
    pbo: number | null;
    bonferroni_z: number | null;
    n_trials: number;
  };
  verdict: string;
}

export interface BookRow {
  book: string;
  net_sharpe: number | null;
  hac_t: number | null;
  turnover: number | null;
  net_beta: number | null;
  max_drawdown: number | null;
}

export interface Construction {
  composite: {
    ic_mean: number | null;
    ic_t: number | null;
    net_sharpe: number | null;
    hac_t: number | null;
    turnover: number | null;
    best_single: string;
    best_single_label: string;
    best_single_sharpe: number | null;
  };
  families: { name: string; neutral_sharpe: number | null; role: string }[];
  riskmodel: BookRow[];
  timing: {
    static_sharpe: number | null;
    timed_sharpe: number | null;
    mkt_raw_sharpe: number | null;
    mkt_raw_dd: number | null;
    mkt_timed_sharpe: number | null;
    mkt_timed_dd: number | null;
    dd_cut: number | null;
  };
  structuring: {
    available: boolean;
    asof?: string;
    n_names?: number;
    vrp_count?: number;
    median_iv?: number | null;
    median_skew?: number | null;
    tail_hedge?: { annual_drag: number | null; cheap_drag: number | null; avg_iv: number | null; median_dte: number | null } | null;
    overwrite?: { symbol: string; atm_iv: number | null; premium_pct: number | null; vrp: number | null }[];
  };
  tax: {
    method: string;
    tax: number | null;
    net_short_term: number | null;
    net_long_term: number | null;
    lt_fraction: number | null;
    wash_disallowed: number | null;
    deferred_gain: number | null;
  }[];
  verdict: string;
}

// ---- Live market-data stream (WebSocket /ws/market) ----

export interface StreamMetrics {
  ready: boolean;
  mid: number;
  microprice: number;
  imbalance: number;
  spreadBps: number;
  microPremiumBps: number;
  bookUpdatesPerSec: number;
  tradesPerSec: number;
  bookAgeMs: number;
  fillRatePct: number;
  avgSlippageBps: number;
  paperOrders: number;
}

export type StreamFrame =
  | { type: 'book'; product: string; quote: ProductQuote; bids: DepthLevel[]; asks: DepthLevel[] }
  | { type: 'trade'; product: string; trades: TradePrint[] }
  | { type: 'metrics'; product: string; metrics: StreamMetrics };

// ---- Fixed-income OTC desk (RFQ), yield curve, bond analytics, tax ----

export interface DealerQuote {
  dealer: string;
  price: number;
  yieldPct: number;
  spreadBps: number;
  size: number;
  best: boolean;
}

export interface Rfq {
  id: string;
  cusip: string;
  description: string;
  side: OrderSide;
  quantity: number;
  tenorYears: number | null;
  curveYieldPct: number | null;
  creditSpreadBps: number | null;
  fairYieldPct: number | null;
  fairClean: number | null;
  quotes: DealerQuote[];
  status: string;
  acceptedDealer: string | null;
  executedOrderRef: string | null;
  createdAt: string;
  expiresAt: string;
}

export interface CreateRfqRequest {
  cusip: string;
  portfolio: string;
  trader: string;
  side: OrderSide;
  quantity: number;
}

export interface RfqExecution {
  rfqId: string;
  orderRef: string;
  dealer: string | null;
  side: OrderSide;
  quantity: number | null;
  price: number | null;
  status: string;
}

export interface YieldCurve {
  asOf: string;
  tenors: number[];
  yields: number[];
  source: string;
}

export interface BondAnalytics {
  cusip: string;
  description: string;
  settlementDate: string;
  cleanPrice: number;
  yieldToMaturityPct: number;
  accruedInterest: number;
  dirtyPrice: number;
  macaulayDuration: number;
  modifiedDuration: number;
  convexity: number;
  dv01: number;
}

export interface TaxTrade {
  time: string;
  side: string;
  quantity: number;
  price: number;
}

export interface TaxRequest {
  assetClass: string;
  lotMethod: string;
  regime: string;
  ordinaryRate?: number;
  longTermRate?: number;
  markPrice?: number;
  trades: TaxTrade[];
}

export interface Disposition {
  acquired: string;
  sold: string;
  quantity: number;
  proceeds: number;
  costBasis: number;
  gain: number;
  holdingDays: number;
  longTerm: boolean;
  washDisallowed: number;
}

export interface TaxReport {
  assetClass: string;
  regime: string;
  lotMethod: string;
  proceeds: number;
  realizedGain: number;
  shortTermGain: number;
  longTermGain: number;
  washSaleDisallowed: number;
  unrealizedMtm: number;
  taxableGain: number;
  taxOwed: number;
  preTaxPnl: number;
  afterTaxPnl: number;
  effectiveTaxRate: number;
  openPosition: number;
  openAvgBasis: number;
  dispositions: Disposition[];
}
