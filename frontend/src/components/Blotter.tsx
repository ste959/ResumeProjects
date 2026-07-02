import { useState } from 'react';
import { api } from '../api/client';
import type { Order } from '../api/types';
import { fmtPrice, fmtQty, fmtTime } from '../util/format';
import { StatusBadge } from './StatusBadge';

interface Props {
  orders: Order[];
  onChanged: () => void;
}

/** The order blotter: every order with its live fill progress and the lifecycle
 *  actions available in its current state. */
export function Blotter({ orders, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);

  async function act(ref: string, fn: () => Promise<unknown>) {
    setBusy(ref);
    try {
      await fn();
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="panel blotter">
      <div className="panel-head">
        <h2>Blotter</h2>
        <span className="count">{orders.length} orders</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Side</th>
              <th>Security</th>
              <th className="num">Qty</th>
              <th className="num">Limit</th>
              <th className="num">Filled</th>
              <th className="num">Avg Px</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 && (
              <tr>
                <td colSpan={9} className="empty">
                  No orders yet — stage one from the ticket.
                </td>
              </tr>
            )}
            {orders.map((o) => {
              const pct = o.quantity ? Math.round((o.filledQuantity / o.quantity) * 100) : 0;
              return (
                <tr key={o.orderRef} title={o.statusReason ?? undefined}>
                  <td className="mono dim">{fmtTime(o.createdAt)}</td>
                  <td className={o.side === 'BUY' ? 'buy' : 'sell'}>{o.side}</td>
                  <td>
                    <div className="sec">{o.cusip}</div>
                    <div className="sec-desc">{o.securityDescription}</div>
                  </td>
                  <td className="num mono">{fmtQty(o.quantity)}</td>
                  <td className="num mono">{o.orderType === 'LIMIT' ? fmtPrice(o.limitPrice) : 'MKT'}</td>
                  <td className="num">
                    <div className="fill-cell">
                      <span className="mono">{fmtQty(o.filledQuantity)}</span>
                      <div className="progress">
                        <div className="progress-bar" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </td>
                  <td className="num mono">{fmtPrice(o.avgFillPrice)}</td>
                  <td>
                    <StatusBadge status={o.status} />
                  </td>
                  <td className="actions">
                    {o.status === 'NEW' && (
                      <button disabled={busy === o.orderRef} onClick={() => act(o.orderRef, () => api.stage(o.orderRef))}>
                        Stage
                      </button>
                    )}
                    {o.status === 'STAGED' && (
                      <button disabled={busy === o.orderRef} onClick={() => act(o.orderRef, () => api.route(o.orderRef))}>
                        Route
                      </button>
                    )}
                    {['NEW', 'STAGED', 'ROUTED', 'PARTIALLY_FILLED'].includes(o.status) && (
                      <button
                        className="danger"
                        disabled={busy === o.orderRef}
                        onClick={() => act(o.orderRef, () => api.cancel(o.orderRef))}
                      >
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
