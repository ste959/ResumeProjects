// Display helpers for bond quantities (par notional) and prices (% of par).

const QTY = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const MONEY = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

export const fmtQty = (n: number): string => QTY.format(n);

export const fmtMoney = (n: number): string => MONEY.format(n);

export const fmtPrice = (n: number | null): string =>
  n == null ? '—' : n.toFixed(4);

export const fmtTime = (iso: string): string =>
  new Date(iso).toLocaleTimeString('en-US', { hour12: false });
