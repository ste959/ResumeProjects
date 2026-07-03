import type { DeskSummary, ExecutionQuality, SecurityVolume } from '../api/types';
import { fmtMoney, fmtPrice, fmtQty } from '../util/format';

interface Props {
  summary: DeskSummary | null;
  execQuality: ExecutionQuality[];
  topSecurities: SecurityVolume[];
}

/**
 * Reporting view driven by the backend's raw-SQL analytics endpoints: desk KPIs, a
 * top-securities-by-volume bar chart (single-series magnitude), and a transaction-cost
 * analysis table (avg fill vs. benchmark, slippage in bps).
 */
export function AnalyticsPanel({ summary, execQuality, topSecurities }: Props) {
  const maxVolume = topSecurities.reduce((m, s) => Math.max(m, s.tradedFace), 0) || 1;

  return (
    <div className="risk">
      <div className="kpi-row">
        <Kpi label="Total Orders" value={summary ? fmtQty(summary.totalOrders) : '—'} />
        <Kpi label="Fill Rate" value={summary ? `${summary.fillRatePct.toFixed(1)}%` : '—'} accent="#059669" />
        <Kpi label="Filled Notional (face)" value={summary ? fmtMoney(summary.totalFilledFace) : '—'} accent="#1d4ed8" />
        <Kpi label="Rejected" value={summary ? fmtQty(summary.rejectedOrders) : '—'}
             accent={summary && summary.rejectedOrders > 0 ? '#dc2626' : undefined} />
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Top Securities by Volume</h2>
          <span className="count">filled par notional</span>
        </div>
        <div className="bars">
          {topSecurities.length === 0 && <div className="empty">No fills yet.</div>}
          {topSecurities.map((s) => (
            <div className="bar-row" key={s.cusip} title={`${s.description}: ${fmtQty(s.tradedFace)} (${s.fillCount} fills)`}>
              <div className="bar-label mono">{s.cusip}</div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(s.tradedFace / maxVolume) * 100}%` }} />
              </div>
              <div className="bar-value mono">{fmtQty(s.tradedFace)}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Execution Quality (TCA)</h2>
          <span className="count">avg fill vs. benchmark</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Security</th>
                <th>Side</th>
                <th className="num">Orders</th>
                <th className="num">Filled</th>
                <th className="num">Avg Fill</th>
                <th className="num">Benchmark</th>
                <th className="num">Slippage (bps)</th>
              </tr>
            </thead>
            <tbody>
              {execQuality.length === 0 && (
                <tr><td colSpan={7} className="empty">No executions yet.</td></tr>
              )}
              {execQuality.map((r) => (
                <tr key={`${r.cusip}-${r.side}`}>
                  <td>
                    <div className="sec">{r.cusip}</div>
                    <div className="sec-desc">{r.description}</div>
                  </td>
                  <td className={r.side === 'BUY' ? 'buy' : 'sell'}>{r.side}</td>
                  <td className="num mono">{fmtQty(r.orderCount)}</td>
                  <td className="num mono">{fmtQty(r.filledFace)}</td>
                  <td className="num mono">{fmtPrice(r.avgFillPrice)}</td>
                  <td className="num mono dim">{fmtPrice(r.benchmarkPrice)}</td>
                  <td className={`num mono ${r.slippageBps > 0 ? 'sell' : r.slippageBps < 0 ? 'buy' : 'dim'}`}>
                    {r.slippageBps > 0 ? '+' : ''}{r.slippageBps.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="tca-note">
          Positive slippage is adverse — a buy filled above, or a sell filled below, its benchmark price.
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
