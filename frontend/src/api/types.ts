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

// ── Quant Desk (Alpaca-backed research → backtest → live) ──
export interface QpAccount {
  status: string | null;
  currency: string;
  equity: number | null;
  last_equity: number | null;
  cash: number | null;
  buying_power: number | null;
  portfolio_value: number | null;
  long_mv: number | null;
  short_mv: number | null;
  pl_today: number | null;
  pl_today_pct: number | null;
  daytrade_count: number | string | null;
  pattern_day_trader: boolean | null;
}
export interface QpClock {
  is_open: boolean;
  next_open: string;
  next_close: string;
  timestamp: string;
}
export interface QpStatus {
  configured: boolean;
  connected: boolean;
  error?: string;
  hint?: string;
  account?: QpAccount;
  clock?: QpClock;
}
export interface QpPosition {
  symbol: string;
  asset_class: string | null;
  side: string;
  qty: number | null;
  avg_entry: number | null;
  current_price: number | null;
  market_value: number | null;
  cost_basis: number | null;
  unrealized_pl: number | null;
  unrealized_plpc: number | null;
  change_today: number | null;
}
export interface QpOrder {
  id: string;
  symbol: string;
  side: string;
  qty: number | null;
  filled_qty: number | null;
  type: string;
  status: string;
  submitted_at: string | null;
  filled_at: string | null;
  filled_avg_price: number | null;
  client_order_id: string | null;
}
export interface QpHistoryPoint {
  t: number;
  equity: number | null;
  pl: number | null;
}
export interface QpHistory {
  configured: boolean;
  error?: string;
  base_value: number | null;
  timeframe?: string;
  points: QpHistoryPoint[];
}
export interface QpStratPosition {
  symbol: string;
  qty: number;
  avg_cost: number;
  realized: number;
  unrealized: number;
  market_value: number;
  n_fills: number;
}
export interface QpStrategy {
  id: string;
  name: string;
  desc: string;
  asset_class: string;
  kind: string;
  symbols: string[];
  realized: number;
  unrealized: number;
  total_pnl: number;
  gross_exposure: number;
  positions: QpStratPosition[];
  n_fills: number;
}
export interface QpAction {
  ts: number;
  kind: string;
  msg: string;
}
export interface QpEngine {
  configured: boolean;
  running: boolean;
  kill: boolean;
  armed: string[];
  last_run: number | null;
  last_error: string | null;
  interval: number;
  strategies: QpStrategy[];
  marks: Record<string, number>;
  actions: QpAction[];
}

// ── Backtest lab ──
export interface LabParamSchema { key: string; label: string; min: number; max: number; default: number; }
export interface LabTemplate { kind: string; name: string; desc: string; params: LabParamSchema[]; code: string; }
export interface LabUniverse { symbol: string; label: string; asset_class: string; promotable: boolean; }
export interface LabTemplates { templates: LabTemplate[]; universe: LabUniverse[]; timeframes: string[]; }
export interface LabCurvePoint { i: number; value: number; }
export interface LabResult {
  ok: boolean;
  reason?: string;
  kind: string;
  symbol: string;
  timeframe: string;
  params: Record<string, number>;
  cost_bps: number;
  n_bars: number;
  bars_per_year: number;
  freq: string;
  window_days: number;
  net_sharpe: number;
  hac_t: number;
  bar_t: number;
  trials: number;
  boot_lo: number | null;
  boot_hi: number | null;
  min_detectable: number;
  underpowered: boolean;
  realistic_cost: boolean;
  live_fee_bps: number;
  total_return: number;
  max_drawdown: number;
  avg_turnover: number;
  hit_rate: number;
  passes: boolean;
  significant: boolean;
  equity_curve: LabCurvePoint[];
  verdict: string;
}
export interface LabPromoteResult { ok: boolean; strategy_id: string; name: string; }

// ── Exploration ──
export interface ScreenerRow {
  symbol: string;
  price: number | null;
  change: number | null;
  percent_change: number | null;
  volume: number | null;
  trade_count: number | null;
}
export interface Screener { most_active: ScreenerRow[]; gainers: ScreenerRow[]; losers: ScreenerRow[]; }
export interface Technicals {
  symbol: string;
  ok: boolean;
  last?: number;
  sma20?: number | null;
  sma50?: number | null;
  trend?: boolean;
  rsi14?: number | null;
  atr14?: number | null;
  atr_pct?: number | null;
  ret_1w?: number | null;
  ret_1m?: number | null;
  ret_3m?: number | null;
  hi?: number;
  lo?: number;
  n?: number;
  spark?: number[];
}
export interface Sector { symbol: string; name: string; price: number | null; change: number | null; }
export interface NewsItem {
  id: number | string;
  headline: string;
  summary: string;
  source: string;
  url: string;
  created_at: string;
  symbols: string[];
}
export interface Catalyst { date: string; days_out: number; close?: string }
export interface Catalysts { fomc: Catalyst[]; next_holiday: Catalyst | null; next_early_close: Catalyst | null; }

// ── Microstructure study (order-flow alpha on an event-driven backtester) ──
export interface MicroDecayPoint {
  horizon: number;
  ic: number;
}
export interface MicroSweepPoint {
  cost_bps: number;
  gross_sharpe: number;
  net_sharpe: number;
  net_bps: number;
  turnover: number;
}
export interface MicroStudy {
  menu: SignalMeta[];
  params: { n: number; ic: number; ret_vol_bps: number; signal: string };
  ic_decay: MicroDecayPoint[];
  cost_sweep: MicroSweepPoint[];
  breakeven_cost_bps: number | null;
  gross_sharpe: number;
  representative: {
    cost_bps: number;
    net_sharpe: number;
    hac_t: number;
    net_bps: number;
    turnover: number;
    hit_rate: number;
  };
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

// ---- Matching engine / exchange (WebSocket /ws/exchange + /api/exchange) ----

export interface ExStats {
  fair: number;
  mid: number;
  spreadBps: number | null;
  mmInventoryLots: number;
  mmInventory: number;
  mmPnl: number;
  mmFills: number;
  ordersPerSec: number;
  tradeCount: number;
  peakOrdersPerSec: number;
  p50LatencyNs: number;
  p99LatencyNs: number;
  restingSize: number;
}

export interface ExLevel { price: number; size: number; orders: number; mm: boolean; you: boolean }
export interface ExQueueOrder { id: number; price: number; size: number; owner: string }
export interface ExTrade { seq: number; price: number; size: number; aggressor: string; maker: string; taker: string }

export interface ExchangeSnapshot {
  instrument: string;
  tickSize: number;
  lotSize: number;
  tick: number;
  stats: ExStats;
  bids: ExLevel[];
  asks: ExLevel[];
  bidQueue: ExQueueOrder[];
  askQueue: ExQueueOrder[];
  trades: ExTrade[];
}

export interface PlaceExRequest {
  side: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET';
  tif?: 'GTC' | 'IOC' | 'FOK';
  postOnly: boolean;
  price?: number;
  size: number;
}

export interface PlaceExResponse {
  orderId: number;
  status: string;
  reason: string | null;
  trades: number;
  filledSize: number;
  restingSize: number;
}

export interface ExPnlAttribution {
  totalUsd: number;
  spreadCapturedUsd: number;
  adverseSelectionUsd: number;
  inventoryUsd: number;
  markedOutFills: number;
}
export interface ExLatencyBucket { depth: string; p50Ns: number; p99Ns: number; count: number }
export interface ExLatencyReport { p50Ns: number; p99Ns: number; maxNs: number; byMatchDepth: ExLatencyBucket[]; note: string }
export interface ExFillView {
  seq: number; tick: number; side: string; price: number; size: number; aggressor: string;
  spreadBps: number; inventory: number; edgeBps: number; markoutBps: number | null;
}
export interface ExSummary { fills: number; adverseFills: number; informedShare: number; avgEdgeBps: number; avgMarkoutBps: number }
export interface ExAnalytics { pnl: ExPnlAttribution; latency: ExLatencyReport; fills: ExFillView[]; summary: ExSummary }

// ---- Rates desk (WebSocket /ws/rates + /api/rates) ----

export interface RaCurve { asOf: string; tenors: number[]; parYields: number[]; zeroRates: number[]; parallelShockBps: number; slopeShockBps: number }
export interface RaQuote { name: string; price: number; fromMidBps: number; best: boolean; us: boolean }
export interface RaRfq {
  instrument: string; side: string; sizeMM: number; nDealers: number; compositeMid: number;
  leakagePx: number; executedPrice: number; winner: string; weWon: boolean; costBps: number;
  competitionPx: number; quotes: RaQuote[];
}
export interface RaDealer { name: string; inventory: number; us: boolean }
export interface RaKr { tenor: number; dv01Usd: number }
export interface RaPosition { instrument: string; positionMM: number; price: number; dv01Usd: number }
export interface RaPnl { totalUsd: number; trading: number; carry: number; rateParallel: number; rateReshape: number; credit: number }
export interface RaBook { valueUsd: number; dv01Usd: number; keyRateDv01: RaKr[]; positions: RaPosition[]; pnl: RaPnl }
export interface RaLeak { dealers: number; avgLeakagePx: number; avgCostBps: number; count: number }
export interface RaCostBySize { bucket: string; avgCostBps: number; count: number }
export interface RaAnalytics { winRatePct: number; ourWins: number; totalRfqs: number; avgCostBps: number; leakageCurve: RaLeak[]; costBySize: RaCostBySize[] }
export interface RatesSnapshot { tick: number; curve: RaCurve; lastRfq: RaRfq | null; dealers: RaDealer[]; book: RaBook; analytics: RaAnalytics }
export interface RatesShockRequest { parallelBps: number; slopeBps: number }
export interface RatesRfqRequest { instrument: string; side: string; sizeMM: number; nDealers: number }

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

export interface ModifyStrategyRequest {
  participation?: number;
  gamma?: number;
  quoteSize?: number;
}

export interface EquityStatus {
  brokerReachable: boolean;
  marketOpen: boolean;
  autoEnabled: boolean;
  targetBook: { asOf: string; names: number } | null;
  positions: { count: number; grossLong: number; grossShort: number; net: number } | null;
  riskCaps: { desk: number; rebalanceBook: number } | null;
  lastRebalance: { time: string | null; status: string; routed: number; skipped: number; rejected: number } | null;
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
