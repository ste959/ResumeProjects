import { useCallback, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { CryptoPosition, DepthLevel, PaperOrder, StreamMetrics } from '../api/types';
import { usePolling } from '../hooks/usePolling';
import { useMarketStream } from '../hooks/useMarketStream';

// The live Microstructure surface — real Coinbase L2 streamed over a WebSocket (not polled): a
// ticking depth ladder, the order-flow tape, a market-making metrics strip, microstructure
// sparklines, and a paper-trade ticket that shows the matching engine's book-sweep fill. The point
// is to make the invisible engine visible — you can watch the book tick and the fills happen.

const PRODUCTS = ['BTC-USD', 'ETH-USD', 'SOL-USD'];

const px = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const sz = (n: number | null | undefined) => (n == null ? '—' : n.toFixed(4));
const signed = (n: number | null | undefined, d = 2) => (n == null ? '—' : (n >= 0 ? '+' : '') + n.toFixed(d));

export function MarketStream() {
  const [product, setProduct] = useState(PRODUCTS[0]);
  const { connected, book, tape, metrics, history } = useMarketStream(product);
  const positions = usePolling(api.cryptoPositions, 3000);
  const [lastFill, setLastFill] = useState<PaperOrder | null>(null);

  const fresh = metrics?.bookAgeMs != null && metrics.bookAgeMs >= 0 && metrics.bookAgeMs < 2000;

  return (
    <main className="risk-main">
      <div className="risk-intro">
        <span className={`dot ${connected ? 'live' : 'down'}`} />
        Real <b>Coinbase Level-2</b> streamed over a <b>WebSocket push</b> (not polling) — the depth
        ladder, order-flow tape and the matching engine, live.
        <span className="ms-product">
          {PRODUCTS.map((p) => (
            <button key={p} className={p === product ? 'active' : ''} onClick={() => setProduct(p)}>{p}</button>
          ))}
        </span>
      </div>

      <MetricsStrip metrics={metrics} connected={connected} fresh={!!fresh} />

      <div className="ms-grid">
        <Ladder bids={book?.bids ?? []} asks={book?.asks ?? []}
          bestBid={book?.quote.bestBid ?? null} bestAsk={book?.quote.bestAsk ?? null}
          spreadBps={book?.quote.spreadBps ?? null} lastFill={lastFill} />
        <FlowPanel product={product} tape={tape} onFilled={setLastFill} lastFill={lastFill} />
        <SignalPanel history={history} />
      </div>

      <Positions positions={positions.data ?? []} />
    </main>
  );
}

// ---- metrics strip ----
function MetricsStrip({ metrics, connected, fresh }: { metrics: StreamMetrics | null; connected: boolean; fresh: boolean }) {
  const m = metrics;
  return (
    <div className="ms-metrics">
      <Metric label="Feed" value={connected ? (fresh ? 'LIVE' : 'STALE') : 'DOWN'}
        tone={connected && fresh ? 'good' : connected ? 'warn' : 'bad'}
        sub={m?.bookAgeMs != null && m.bookAgeMs >= 0 ? `${m.bookAgeMs}ms old` : 'no data'} />
      <Metric label="Spread" value={m ? `${signed(m.spreadBps)} bps`.replace('+', '') : '—'} sub="ask − bid" />
      <Metric label="Imbalance" value={m ? signed(m.imbalance, 2) : '—'} tone={m ? (m.imbalance >= 0 ? 'good' : 'bad') : undefined} sub="(bid−ask)/(bid+ask)" />
      <Metric label="Microprice prem" value={m ? `${signed(m.microPremiumBps)} bps` : '—'} tone={m ? (m.microPremiumBps >= 0 ? 'good' : 'bad') : undefined} sub="fair vs mid" />
      <Metric label="Book updates" value={m ? `${m.bookUpdatesPerSec}/s` : '—'} sub="L2 throughput" />
      <Metric label="Trade flow" value={m ? `${m.tradesPerSec}/s` : '—'} sub="prints/sec" />
      <Metric label="Paper fills" value={m && m.paperOrders > 0 ? `${m.fillRatePct}%` : '—'}
        sub={m && m.paperOrders > 0 ? `${signed(m.avgSlippageBps)} bps slip` : 'no orders'} />
    </div>
  );
}

function Metric({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'good' | 'bad' | 'warn' }) {
  return (
    <div className="ms-metric">
      <span className="msm-label">{label}</span>
      <span className={`msm-value ${tone ?? ''}`}>{value}</span>
      {sub && <span className="msm-sub">{sub}</span>}
    </div>
  );
}

// ---- L2 ladder (streaming) ----
function Ladder({ bids, asks, bestBid, bestAsk, spreadBps, lastFill }: {
  bids: DepthLevel[]; asks: DepthLevel[]; bestBid: number | null; bestAsk: number | null;
  spreadBps: number | null; lastFill: PaperOrder | null;
}) {
  const rows = 10;
  const shownAsks = asks.slice(0, rows);
  const shownBids = bids.slice(0, rows);
  const maxCum = Math.max(
    ...shownAsks.map((l) => l.cumulative), ...shownBids.map((l) => l.cumulative), 1,
  );
  // Prices swept by the most recent paper fill, to highlight what the engine consumed.
  const sweptPrices = useMemo(() => new Set((lastFill?.fills ?? []).map((f) => f.price)), [lastFill]);

  return (
    <div className="panel ms-ladder">
      <div className="panel-head"><h2>L2 Order Book</h2><span className="count">depth · streaming</span></div>
      <div className="ladder-body">
        {shownAsks.slice().reverse().map((l, i) => (
          <LadderRow key={`a${i}`} level={l} side="ask" maxCum={maxCum} swept={sweptPrices.has(l.price)} />
        ))}
        <div className="ladder-mid">
          <span className="lm-bid">{px(bestBid)}</span>
          <span className="lm-spread">{spreadBps == null ? '—' : `${spreadBps.toFixed(2)} bps`}</span>
          <span className="lm-ask">{px(bestAsk)}</span>
        </div>
        {shownBids.map((l, i) => (
          <LadderRow key={`b${i}`} level={l} side="bid" maxCum={maxCum} swept={sweptPrices.has(l.price)} />
        ))}
        {shownAsks.length === 0 && <div className="empty">waiting for the book…</div>}
      </div>
    </div>
  );
}

function LadderRow({ level, side, maxCum, swept }: { level: DepthLevel; side: 'bid' | 'ask'; maxCum: number; swept: boolean }) {
  const w = Math.min(100, (level.cumulative / maxCum) * 100);
  return (
    <div className={`ladder-row ${side} ${swept ? 'swept' : ''}`}>
      <div className={`depth-bar ${side}`} style={{ width: `${w}%` }} />
      <span className="lr-price">{px(level.price)}</span>
      <span className="lr-size">{sz(level.size)}</span>
      <span className="lr-cum">{sz(level.cumulative)}</span>
    </div>
  );
}

// ---- order-flow + matching engine ----
function FlowPanel({ product, tape, onFilled, lastFill }: {
  product: string; tape: { seq?: number; price: number; size: number; side: string; time: string }[];
  onFilled: (o: PaperOrder) => void; lastFill: PaperOrder | null;
}) {
  const [size, setSize] = useState('0.01');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = useCallback(async (side: 'BUY' | 'SELL') => {
    setBusy(true);
    setErr(null);
    try {
      const order = await api.submitPaperOrder(product, { side, type: 'MARKET', size: Number(size) });
      onFilled(order);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }, [product, size, onFilled]);

  return (
    <div className="panel ms-flow">
      <div className="panel-head"><h2>Order Flow &amp; Engine</h2><span className="count">market → match → fill</span></div>
      <div className="flow-ticket">
        <input value={size} onChange={(e) => setSize(e.target.value)} inputMode="decimal" aria-label="Size" />
        <button className="buy" disabled={busy} onClick={() => submit('BUY')}>Buy</button>
        <button className="sell" disabled={busy} onClick={() => submit('SELL')}>Sell</button>
      </div>
      {err && <div className="flow-err">{err}</div>}
      {lastFill && <FillSweep order={lastFill} />}

      <div className="flow-tape-head">Live tape — market orders hitting the book</div>
      <div className="flow-tape">
        {tape.length === 0 && <div className="empty">waiting for prints…</div>}
        {tape.map((t) => (
          <div key={t.seq ?? `${t.time}-${t.price}`} className={`tape-row ${t.side?.toLowerCase() === 'buy' ? 'buy' : 'sell'}`}>
            <span className="tr-side">{t.side?.toUpperCase() === 'BUY' ? '▲' : '▼'}</span>
            <span className="tr-price">{px(t.price)}</span>
            <span className="tr-size">{sz(t.size)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Shows how the paper order swept the book, level by level — the matching engine made visible. */
function FillSweep({ order }: { order: PaperOrder }) {
  const filled = order.fills && order.fills.length > 0;
  return (
    <div className={`fill-sweep ${order.side.toLowerCase()}`}>
      <div className="fs-head">
        <span className="fs-tag">{order.side} {sz(order.requestedSize)}</span>
        <span className="fs-status">{order.status}</span>
      </div>
      {filled ? (
        <>
          <div className="fs-levels">
            {order.fills.map((f, i) => (
              <span key={i} className="fs-level">{px(f.price)} × {sz(f.size)}</span>
            ))}
          </div>
          <div className="fs-summary">
            VWAP <b>{px(order.avgPrice)}</b> · slippage <b>{signed(order.slippageBps)} bps</b>{' '}
            across {order.fills.length} level{order.fills.length > 1 ? 's' : ''}
          </div>
        </>
      ) : <div className="fs-summary">no fill (unmarketable / empty book)</div>}
    </div>
  );
}

// ---- microstructure sparklines ----
function SignalPanel({ history }: { history: StreamMetrics[] }) {
  return (
    <div className="panel ms-signals">
      <div className="panel-head"><h2>Microstructure</h2><span className="count">rolling</span></div>
      <div className="sig-body">
        <SparkRow label="Order-book imbalance" values={history.map((h) => h.imbalance)} zero color="var(--accent)" fmt={(v) => signed(v, 2)} />
        <SparkRow label="Microprice premium (bps)" values={history.map((h) => h.microPremiumBps)} zero color="var(--violet)" fmt={(v) => signed(v, 2)} />
        <SparkRow label="Spread (bps)" values={history.map((h) => h.spreadBps)} color="var(--warn)" fmt={(v) => v.toFixed(2)} />
      </div>
    </div>
  );
}

function SparkRow({ label, values, color, zero = false, fmt }: {
  label: string; values: number[]; color: string; zero?: boolean; fmt: (v: number) => string;
}) {
  const last = values.length ? values[values.length - 1] : null;
  return (
    <div className="sig-row">
      <div className="sig-top"><span>{label}</span><span className="sig-val" style={{ color }}>{last == null ? '—' : fmt(last)}</span></div>
      <Spark values={values} color={color} zero={zero} />
    </div>
  );
}

function Spark({ values, color, zero = false }: { values: number[]; color: string; zero?: boolean }) {
  if (values.length < 2) return <div className="empty sm">collecting…</div>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const h = 34;
  const w = 100;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / range) * h}`).join(' ');
  const zeroY = zero ? h - ((0 - min) / range) * h : null;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {zeroY != null && zeroY >= 0 && zeroY <= h && <line x1={0} x2={w} y1={zeroY} y2={zeroY} className="spark-zero" />}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// ---- positions ----
function Positions({ positions }: { positions: CryptoPosition[] }) {
  if (positions.length === 0) return null;
  return (
    <div className="panel ms-positions">
      <div className="panel-head"><h2>Crypto Positions</h2><span className="count">live mark-to-market</span></div>
      <div className="tablewrap">
        <table className="data-table">
          <thead><tr><th>Product</th><th className="r">Net</th><th className="r">Avg cost</th><th className="r">Mark</th><th className="r">Unrealized</th></tr></thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.product}>
                <td>{p.product}</td>
                <td className="r mono">{sz(p.netSize)}</td>
                <td className="r mono dim">{px(p.avgCost)}</td>
                <td className="r mono">{px(p.markPrice)}</td>
                <td className={`r mono ${(p.unrealizedPnl ?? 0) >= 0 ? 'pos' : 'neg'}`}>{signed(p.unrealizedPnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
