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

export interface ApiError {
  timestamp: string;
  status: number;
  error: string;
  message: string;
  path: string;
  fieldErrors?: Record<string, string>;
}
