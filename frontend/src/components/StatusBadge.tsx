import type { OrderStatus } from '../api/types';

/** Colour-coded pill for an order's lifecycle status. */
export function StatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`badge badge-${status.toLowerCase()}`}>{status.replace('_', ' ')}</span>;
}
