import type { DeskRiskSummary } from '../api/types';
import { fmtMoney, fmtQty } from '../util/format';

/**
 * Live desk-risk view, fed entirely by the risk microservice's aggregation of the
 * Kafka order-event stream (nothing here calls the OMS directly). Headline figures are
 * stat tiles; the status mix is a labelled distribution bar using the reserved status
 * palette; per-portfolio detail is a table.
 */

// Fixed status order + reserved status colours, matching the blotter's badges so the
// same state reads the same colour everywhere. Colour is never the only cue — every
// status is labelled in the legend and table.
const STATUS_ORDER: { key: string; label: string; color: string }[] = [
  { key: 'NEW', label: 'New', color: '#94a3b8' },
  { key: 'STAGED', label: 'Staged', color: '#1d4ed8' },
  { key: 'ROUTED', label: 'Routed', color: '#7c3aed' },
  { key: 'PARTIALLY_FILLED', label: 'Partially Filled', color: '#f59e0b' },
  { key: 'FILLED', label: 'Filled', color: '#059669' },
  { key: 'CANCELLED', label: 'Cancelled', color: '#cbd5e1' },
  { key: 'REJECTED', label: 'Rejected', color: '#dc2626' },
];

export function RiskDashboard({ summary }: { summary: DeskRiskSummary | null }) {
  if (!summary) {
    return <div className="panel"><div className="empty">Loading desk risk…</div></div>;
  }

  const byStatus = summary.ordersByStatus ?? {};
  const total = summary.totalOrders || 0;
  const working = STATUS_ORDER
    .filter((s) => ['NEW', 'STAGED', 'ROUTED', 'PARTIALLY_FILLED'].includes(s.key))
    .reduce((sum, s) => sum + (byStatus[s.key] ?? 0), 0);
  const rejected = byStatus['REJECTED'] ?? 0;

  // Only statuses actually present, in fixed order — so a colour always maps to one state.
  const present = STATUS_ORDER.filter((s) => (byStatus[s.key] ?? 0) > 0);

  return (
    <div className="risk">
      <div className="kpi-row">
        <Kpi label="Total Orders" value={fmtQty(total)} />
        <Kpi label="Filled Notional (face)" value={fmtMoney(summary.totalFilledFace)} accent="#059669" />
        <Kpi label="Working Orders" value={fmtQty(working)} accent="#1d4ed8" />
        <Kpi label="Rejected" value={fmtQty(rejected)} accent={rejected > 0 ? '#dc2626' : undefined} />
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Order Status Distribution</h2>
          <span className="count">{total} orders</span>
        </div>
        <div className="dist-body">
          {total === 0 ? (
            <div className="empty">No orders on the tape yet.</div>
          ) : (
            <>
              <div className="dist-bar" role="img" aria-label="Order status distribution">
                {present.map((s) => {
                  const count = byStatus[s.key] ?? 0;
                  const pct = (count / total) * 100;
                  return (
                    <div
                      key={s.key}
                      className="dist-seg"
                      style={{ width: `${pct}%`, background: s.color }}
                      title={`${s.label}: ${count} (${pct.toFixed(0)}%)`}
                    >
                      {pct >= 8 && <span className="dist-seg-label">{count}</span>}
                    </div>
                  );
                })}
              </div>
              <div className="legend">
                {present.map((s) => (
                  <span key={s.key} className="legend-item">
                    <span className="swatch" style={{ background: s.color }} />
                    {s.label}
                    <b>{byStatus[s.key]}</b>
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Risk by Portfolio</h2>
          <span className="count">{summary.portfolios.length} portfolios</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Portfolio</th>
                <th className="num">Orders</th>
                <th className="num">Working</th>
                <th className="num">Rejected</th>
                <th className="num">Filled Notional (face)</th>
              </tr>
            </thead>
            <tbody>
              {summary.portfolios.length === 0 && (
                <tr><td colSpan={5} className="empty">No portfolios yet.</td></tr>
              )}
              {summary.portfolios.map((p) => (
                <tr key={p.portfolio}>
                  <td className="sec">{p.portfolio}</td>
                  <td className="num mono">{fmtQty(p.orderCount)}</td>
                  <td className="num mono">{fmtQty(p.workingOrders)}</td>
                  <td className={`num mono ${p.rejectedOrders > 0 ? 'sell' : 'dim'}`}>{fmtQty(p.rejectedOrders)}</td>
                  <td className="num mono">{fmtMoney(p.filledFace)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={accent ? { color: accent } : undefined}>{value}</div>
    </div>
  );
}
