import type {
  CreateOrderRequest,
  DeskRiskSummary,
  Order,
  Position,
  Security,
  ApiError,
} from './types';

// In dev, requests go to /api and Vite proxies them to the backend. In a built
// deployment, VITE_API_BASE can point at the API gateway.
const BASE = (import.meta.env.VITE_API_BASE ?? '') + '/api';
// The risk microservice is exposed under /risk by the dev proxy and nginx.
const RISK_BASE = (import.meta.env.VITE_API_BASE ?? '') + '/risk';

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
  securities: () => request<Security[]>('/securities'),

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
};
