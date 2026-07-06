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

export interface Security {
  cusip: string;
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
