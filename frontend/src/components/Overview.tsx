import { api } from '../api/client';
import { usePolling } from '../hooks/usePolling';

const usd = (n: number | null | undefined, dp = 2) =>
  n == null ? '—' : n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: dp });
const num = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString());

/**
 * Platform cockpit: a single glance across every desk — fixed-income flow, live crypto
 * markets, running strategies, and the research layer — with jump-off links. The piece
 * that makes the separate areas read as one intentional platform.
 */
export function Overview({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const desk = usePolling(api.deskSummary, 3000);
  const risk = usePolling(api.riskSummary, 3000);
  const quotes = usePolling(api.marketProducts, 2000);
  const runs = usePolling(api.strategies, 2000);

  const activeRuns = (runs.data ?? []).filter((r) => r.status === 'RUNNING');
  const stratPnl = (runs.data ?? []).reduce((s, r) => s + (r.totalPnl ?? 0), 0);

  return (
    <div className="overview">
      {/* Fixed income */}
      <section className="ov-section" onClick={() => onNavigate('trading')} role="button" tabIndex={0}>
        <div className="ov-head"><h2>Fixed Income Desk</h2><span className="ov-go">Open desk →</span></div>
        <div className="kpi-row">
          <Kpi label="Total Orders" value={desk.data ? num(desk.data.totalOrders) : '—'} />
          <Kpi label="Fill Rate" value={desk.data ? `${desk.data.fillRatePct.toFixed(1)}%` : '—'} accent="#059669" />
          <Kpi label="Filled Notional" value={desk.data ? usd(desk.data.totalFilledFace, 0) : '—'} accent="#1d4ed8" />
          <Kpi label="Working / Rejected"
               value={risk.data ? `${risk.data.portfolios.reduce((s, p) => s + p.workingOrders, 0)} / ${risk.data.portfolios.reduce((s, p) => s + p.rejectedOrders, 0)}` : '—'} />
        </div>
      </section>

      {/* Live markets */}
      <section className="ov-section" onClick={() => onNavigate('market')} role="button" tabIndex={0}>
        <div className="ov-head"><h2>Live Markets · Coinbase</h2><span className="ov-go">Open market →</span></div>
        <div className="kpi-row">
          {(quotes.data ?? []).map((q) => (
            <div className="kpi" key={q.product}>
              <div className="kpi-label">{q.product}</div>
              <div className="kpi-value" style={{ fontSize: 22 }}>{usd(q.lastPrice)}</div>
              <div className="kpi-sub">spread {q.spreadBps ?? '—'} bps</div>
            </div>
          ))}
          {(quotes.data ?? []).length === 0 && <Kpi label="Feed" value="connecting…" />}
        </div>
      </section>

      {/* Strategies */}
      <section className="ov-section" onClick={() => onNavigate('strategies')} role="button" tabIndex={0}>
        <div className="ov-head"><h2>Strategy Engine</h2><span className="ov-go">Open strategies →</span></div>
        <div className="kpi-row">
          <Kpi label="Active Runs" value={num(activeRuns.length)} accent="#1d4ed8" />
          <Kpi label="Total P&L" value={usd(stratPnl)} accent={stratPnl >= 0 ? '#059669' : '#dc2626'} />
          <Kpi label="Runs" value={num((runs.data ?? []).length)} />
          <Kpi label="Types" value="TWAP · POV · A–C · A–S" />
        </div>
      </section>

      {/* Research */}
      <section className="ov-section research-card">
        <div className="ov-head"><h2>Quant Research (Python)</h2><span className="ov-go dim">offline · research/</span></div>
        <p className="ov-note">
          A DuckDB/Parquet warehouse with hand-rolled econometrics (cointegration, OU half-life) and a
          cost-aware backtester. The BTC/ETH stat-arb study reports an <b>honest verdict</b>: strong
          in-sample Sharpe but no cointegration → flagged as likely overfit, not alpha.
        </p>
      </section>
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
