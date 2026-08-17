import { api } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import { Term } from './Term';

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
      <section className="ov-intro">
        <h1 className="ov-title">Trading platform</h1>
        <p>
          A live crypto market you can watch, a fixed-income desk where orders are placed and tracked,
          and a research lab that tests strategies. Under the finance it's a low-latency{' '}
          <Term>matching engine</Term>, event-driven microservices, and a signal compiler. New to the
          terms? Hover any <span className="term-hint">dotted</span> word — or read the 3-minute primer
          in <code>docs/domain-primer.md</code>.
        </p>
      </section>

      {/* Fixed income */}
      <section className="ov-section clickable">
        <div className="ov-head"><h2>Fixed Income Desk</h2>
          <button type="button" className="ov-go" onClick={() => onNavigate('trading')}>Open desk →</button></div>
        <p className="ov-explain">Place bond orders and watch them move through compliance, matching, and
          settlement — an order-lifecycle state machine. <Term>Fill rate</Term> is the share that traded.</p>
        <div className="kpi-row">
          <Kpi label="Total Orders" value={desk.data ? num(desk.data.totalOrders) : '—'} />
          <Kpi label="Fill Rate" value={desk.data ? `${desk.data.fillRatePct.toFixed(1)}%` : '—'} accent="#059669" />
          <Kpi label="Filled Notional" value={desk.data ? usd(desk.data.totalFilledFace, 0) : '—'} accent="#1d4ed8" />
          <Kpi label="Working / Rejected"
               value={risk.data ? `${risk.data.portfolios.reduce((s, p) => s + p.workingOrders, 0)} / ${risk.data.portfolios.reduce((s, p) => s + p.rejectedOrders, 0)}` : '—'} />
        </div>
      </section>

      {/* Live markets */}
      <section className="ov-section clickable">
        <div className="ov-head"><h2>Live Markets · Coinbase</h2>
          <button type="button" className="ov-go" onClick={() => onNavigate('market')}>Open market →</button></div>
        <p className="ov-explain">Real-time prices from a live exchange feed. Each tile is an instrument's
          last price and its <Term>spread</Term> (the bid–ask gap).</p>
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
      <section className="ov-section clickable">
        <div className="ov-head"><h2>Strategy Engine</h2>
          <button type="button" className="ov-go" onClick={() => onNavigate('strategies')}>Open strategies →</button></div>
        <p className="ov-explain">Automated trading strategies (execution algos + a <Term>market maker</Term>)
          running live, with their running P&amp;L.</p>
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
          A DuckDB/Parquet warehouse with hand-rolled econometrics (<Term>cointegration</Term>, OU
          half-life) and a cost-aware <Term>backtest</Term>er. The BTC/ETH <Term>stat-arb</Term> study
          reports an <b>honest verdict</b>: strong in-sample <Term>Sharpe</Term> but no cointegration →
          flagged as likely overfit, not alpha.
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
