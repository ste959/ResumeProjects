import { useMemo } from 'react';
import { api } from '../api/client';
import type { QpHistory, QpHistoryPoint, QpPosition, QpStatus } from '../api/types';
import { usePolling } from '../hooks/usePolling';

// Live Strategies — the crown jewel: a real Alpaca paper account. Phase 1 shows the raw account
// (equity curve, positions, orders) so the pipe is proven end-to-end. Per-strategy attribution and
// the strategy engine land in Phase 2 — this is the honest account it will decompose.

const money = (n: number | null | undefined, dp = 2) =>
  n == null ? '—' : (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const sgn = (n: number | null | undefined) =>
  n == null ? '—' : (n >= 0 ? '+' : '-') + '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n: number | null | undefined) => (n == null ? '—' : (n >= 0 ? '+' : '') + (n * 100).toFixed(2) + '%');
const qty = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 6 }));
const clsOf = (n: number | null | undefined) => (n == null ? '' : n >= 0 ? 'pos' : 'neg');

export function LiveTab() {
  const histFetch = useMemo(() => () => api.qpHistory('1M', '1D'), []);
  const status = usePolling<QpStatus>(api.qpStatus, 8000);
  const positions = usePolling<QpPosition[]>(api.qpPositions, 6000);
  const orders = usePolling(api.qpOrders, 12000);
  const history = usePolling<QpHistory>(histFetch, 30000);

  const s = status.data;

  // Not configured / not connected → a clean "connect Alpaca" gate, not an error dump.
  if (s && !s.connected) {
    return <ConnectGate status={s} />;
  }
  if (!s) {
    return <main className="live-main"><div className="live-loading">connecting to Alpaca…</div></main>;
  }

  const a = s.account!;
  const clk = s.clock;
  const pos = (positions.data ?? []).slice().sort((x, y) => Math.abs(y.market_value ?? 0) - Math.abs(x.market_value ?? 0));
  const gross = pos.reduce((t, p) => t + Math.abs(p.market_value ?? 0), 0);
  const net = pos.reduce((t, p) => t + (p.market_value ?? 0), 0);

  return (
    <main className="live-main">
      <div className="live-intro">
        <span className={`dot ${s.connected ? 'live' : 'down'}`} />
        Live <b>Alpaca paper</b> account — real orders, real fills, paper money.
        <MarketPill clk={clk} />
      </div>

      {/* account header */}
      <div className="live-head">
        <div className="live-equity">
          <span className="lh-label">Account equity</span>
          <span className="lh-equity">{money(a.equity)}</span>
          <span className={`lh-plt ${clsOf(a.pl_today)}`}>{sgn(a.pl_today)} ({pct(a.pl_today_pct)}) today</span>
        </div>
        <div className="live-kpis">
          <Kpi label="Buying power" value={money(a.buying_power, 0)} />
          <Kpi label="Cash" value={money(a.cash, 0)} />
          <Kpi label="Long / Short" value={`${money(a.long_mv, 0)} / ${money(a.short_mv, 0)}`} />
          <Kpi label="Gross / Net expo" value={`${money(gross, 0)} / ${money(net, 0)}`} />
        </div>
      </div>

      {/* equity curve */}
      <section className="live-card">
        <div className="live-card-head">
          <h3>Portfolio equity</h3>
          <span>paper account value over time · from Alpaca portfolio history</span>
        </div>
        <EquityArea history={history.data} />
      </section>

      {/* positions */}
      <section className="live-card">
        <div className="live-card-head">
          <h3>Positions <span className="live-count">{pos.length}</span></h3>
          <span>marked to the live price · unrealized P&L</span>
        </div>
        {pos.length === 0 ? (
          <div className="live-empty">No open positions. The strategy engine (Phase 2) will populate this;
            for now you can place a paper order from the Alpaca dashboard and watch it appear here live.</div>
        ) : (
          <div className="tablewrap">
            <table className="data-table live-table">
              <thead>
                <tr>
                  <th>Symbol</th><th>Side</th><th className="r">Qty</th><th className="r">Avg entry</th>
                  <th className="r">Last</th><th className="r">Mkt value</th><th className="r">Unreal. P&L</th>
                  <th className="r">%</th><th className="r">Today</th>
                </tr>
              </thead>
              <tbody>
                {pos.map((p) => (
                  <tr key={p.symbol}>
                    <td className="mono b">{p.symbol}</td>
                    <td><span className={`side-tag ${p.side === 'long' ? 'buy' : 'sell'}`}>{p.side}</span></td>
                    <td className="r mono">{qty(p.qty)}</td>
                    <td className="r mono">{money(p.avg_entry)}</td>
                    <td className="r mono">{money(p.current_price)}</td>
                    <td className="r mono">{money(p.market_value, 0)}</td>
                    <td className={`r mono ${clsOf(p.unrealized_pl)}`}>{sgn(p.unrealized_pl)}</td>
                    <td className={`r mono ${clsOf(p.unrealized_plpc)}`}>{pct(p.unrealized_plpc)}</td>
                    <td className={`r mono ${clsOf(p.change_today)}`}>{pct(p.change_today)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* orders */}
      <section className="live-card">
        <div className="live-card-head">
          <h3>Recent orders</h3>
          <span>newest first · any status</span>
        </div>
        {(orders.data ?? []).length === 0 ? (
          <div className="live-empty">No orders yet.</div>
        ) : (
          <div className="tablewrap">
            <table className="data-table live-table">
              <thead>
                <tr>
                  <th>Time</th><th>Symbol</th><th>Side</th><th className="r">Qty</th><th className="r">Filled</th>
                  <th>Type</th><th className="r">Avg px</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(orders.data ?? []).map((o) => (
                  <tr key={o.id}>
                    <td className="mono dim">{fmtTime(o.submitted_at)}</td>
                    <td className="mono b">{o.symbol}</td>
                    <td><span className={`side-tag ${o.side === 'buy' ? 'buy' : 'sell'}`}>{o.side}</span></td>
                    <td className="r mono">{qty(o.qty)}</td>
                    <td className="r mono">{qty(o.filled_qty)}</td>
                    <td className="dim">{o.type}</td>
                    <td className="r mono">{o.filled_avg_price == null ? '—' : money(o.filled_avg_price)}</td>
                    <td><span className={`ord-status s-${o.status}`}>{o.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="live-foot">
        Next (Phase 2): a strategy engine that submits orders tagged by strategy, so this account breaks
        down into <b>per-strategy P&L</b> — which strategy is buying what, and how each is performing.
      </p>
    </main>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return <div className="live-kpi"><span>{label}</span><b>{value}</b></div>;
}

function MarketPill({ clk }: { clk?: QpStatus['clock'] }) {
  if (!clk) return null;
  const when = clk.is_open ? `closes ${fmtTime(clk.next_close)}` : `opens ${fmtTime(clk.next_open)}`;
  return <span className={`mkt-pill ${clk.is_open ? 'open' : 'closed'}`}>{clk.is_open ? 'MARKET OPEN' : 'MARKET CLOSED'} · {when}</span>;
}

function ConnectGate({ status }: { status: QpStatus }) {
  return (
    <main className="live-main">
      <div className="connect-card">
        <div className="connect-mark">∿</div>
        <h2>{status.configured ? 'Alpaca keys set, but the connection failed' : 'Connect your Alpaca paper account'}</h2>
        {status.configured ? (
          <p className="connect-err">{status.error}</p>
        ) : (
          <p>The Live desk trades a real <b>Alpaca paper</b> account (fake money, real API). Add your keys and
            this tab lights up with your equity, positions, and orders.</p>
        )}
        <ol className="connect-steps">
          <li>Sign up at <span className="mono">alpaca.markets</span> → it defaults to a <b>Paper</b> account.</li>
          <li>Dashboard → <b>Paper Trading</b> → <b>API Keys</b> → <b>Generate</b>. Copy the Key ID and Secret.</li>
          <li>Create <span className="mono">.env</span> in the repo root:
            <pre className="connect-env">ALPACA_API_KEY=your-key-id{'\n'}ALPACA_API_SECRET=your-secret-key{'\n'}ALPACA_PAPER=true</pre>
          </li>
          <li>Restart the research service: <span className="mono">docker compose restart research-service</span></li>
        </ol>
        {status.hint && <p className="connect-hint">{status.hint}</p>}
      </div>
    </main>
  );
}

/** Portfolio equity area chart with a $ axis and a labeled start value. */
function EquityArea({ history }: { history: QpHistory | null | undefined }) {
  const pts = (history?.points ?? []).filter((p): p is QpHistoryPoint & { equity: number } => p.equity != null);
  if (pts.length < 2) {
    return <div className="live-empty" style={{ margin: '4px 0 0' }}>
      {history && history.points.length === 0 ? 'No equity history yet — it fills in as the account trades.' : 'loading equity curve…'}
    </div>;
  }
  const W = 900, H = 220, m = { l: 62, r: 16, t: 14, b: 26 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const vals = pts.map((p) => p.equity);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo || 1) * 0.08;
  const yLo = lo - pad, yHi = hi + pad;
  const x = (i: number) => m.l + (i / (pts.length - 1)) * pw;
  const y = (v: number) => m.t + (1 - (v - yLo) / (yHi - yLo)) * ph;
  const up = pts[pts.length - 1].equity >= pts[0].equity;
  const color = up ? 'var(--buy)' : 'var(--sell)';
  const line = pts.map((p, i) => `${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join(' ');
  const area = `${x(0).toFixed(1)},${(m.t + ph).toFixed(1)} ${line} ${x(pts.length - 1).toFixed(1)},${(m.t + ph).toFixed(1)}`;
  const yTicks = Array.from({ length: 4 }, (_, k) => yLo + (k / 3) * (yHi - yLo));
  const base = history?.base_value ?? pts[0].equity;
  return (
    <svg className="eqchart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="portfolio equity">
      {yTicks.map((v, k) => (
        <g key={k}>
          <line className="eqc-grid" x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} />
          <text className="eqc-tick" x={m.l - 6} y={y(v) + 3} textAnchor="end">${(v / 1000).toFixed(1)}k</text>
        </g>
      ))}
      {base >= yLo && base <= yHi && (
        <>
          <line className="eqc-base" x1={m.l} x2={W - m.r} y1={y(base)} y2={y(base)} />
          <text className="eqc-tick" x={W - m.r} y={y(base) - 4} textAnchor="end" style={{ fill: 'var(--muted)' }}>start ${(base / 1000).toFixed(0)}k</text>
        </>
      )}
      <polygon points={area} fill={color} fillOpacity={0.1} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
