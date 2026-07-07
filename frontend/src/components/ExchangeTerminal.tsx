import { useCallback, useState } from 'react';
import { api } from '../api/client';
import type { ExLevel, ExQueueOrder, ExStats, ExTrade } from '../api/types';
import { useExchangeStream } from '../hooks/useExchangeStream';

// The one screen: our matching engine, live. A price-time-priority limit order book you can watch
// match in real time — the market maker and agent flow trade continuously, and you can place your
// own orders and see them rest in the queue or cross and fill. Built to be read, not flash-banged:
// a title that says what it is, a labeled stats strip, the book as the obvious focal point, and the
// order flow + entry beside it.

const usd = (n: number) => '$' + Math.round(n).toLocaleString('en-US');
const usd2 = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(n).toFixed(2);
const btc = (n: number) => n.toFixed(3);
const sBtc = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(3);
const lat = (ns: number) => (ns >= 1000 ? (ns / 1000).toFixed(2) + 'µs' : ns + 'ns');
const rate = (n: number) => (n >= 1000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1) + 'k' : String(Math.round(n)));

interface MyOrder { id: number; side: string; price: number; size: number }

export function ExchangeTerminal() {
  const { connected, snapshot, tradedPrices } = useExchangeStream();
  const [myOrders, setMyOrders] = useState<MyOrder[]>([]);

  const onPlaced = useCallback((o: MyOrder | null) => {
    if (o) setMyOrders((prev) => [o, ...prev].slice(0, 12));
  }, []);
  const onCancel = useCallback(async (id: number) => {
    await api.cancelExchangeOrder(id).catch(() => {});
    setMyOrders((prev) => prev.filter((o) => o.id !== id));
  }, []);

  return (
    <div className="xt">
      <header className="xt-head">
        <div className="xt-title">
          <span className="xt-logo">◧</span>
          <div>
            <h1>Matching Engine <span className="xt-inst">· BTC-USD</span></h1>
            <p>
              A price-time-priority central limit order book — <b>our engine, live</b>. Real BTC price ·
              simulated order flow · every match is ours. Place an order and watch it rest in the queue or cross and fill.
            </p>
          </div>
        </div>
        <span className={`xt-conn ${connected ? 'up' : 'down'}`}>
          <span className="dot" /> {connected ? 'LIVE' : 'connecting…'}
        </span>
      </header>

      {!snapshot ? (
        <div className="xt-loading">connecting to the matching engine…</div>
      ) : (
        <>
          <StatsStrip s={snapshot.stats} />
          <div className="xt-grid">
            <OrderBook bids={snapshot.bids} asks={snapshot.asks} stats={snapshot.stats} traded={tradedPrices} />
            <div className="xt-side">
              <OrderEntry mid={snapshot.stats.mid} onPlaced={onPlaced} myOrders={myOrders} onCancel={onCancel} />
              <Tape trades={snapshot.trades} />
            </div>
          </div>
          <Queue bidQueue={snapshot.bidQueue} askQueue={snapshot.askQueue} />
        </>
      )}
    </div>
  );
}

// ── stats strip ───────────────────────────────────────────────────────────────────────────────
function StatsStrip({ s }: { s: ExStats }) {
  return (
    <div className="xt-stats">
      <Stat label="Mid price" value={usd(s.mid)} sub={`fair ${usd(s.fair)} · tracks live BTC`} />
      <Stat label="Spread" value={s.spreadBps == null ? '—' : `${s.spreadBps.toFixed(1)} bps`} sub="best ask − best bid" />
      <Stat label="Maker inventory" value={`${sBtc(s.mmInventory)}`} sub="BTC · skewed back to flat" tone={Math.abs(s.mmInventory) < 0.05 ? 'good' : 'warn'} />
      <Stat label="Maker P&L" value={usd2(s.mmPnl)} sub={`${s.mmFills.toLocaleString()} fills · spread − adverse sel.`} tone={s.mmPnl >= 0 ? 'good' : 'bad'} />
      <Stat label="Throughput" value={`${rate(s.peakOrdersPerSec)}/s`} sub={`benchmarked · live ${rate(s.ordersPerSec)}/s`} accent />
      <Stat label="Match latency" value={lat(s.p50LatencyNs)} sub={`p50 · p99 ${lat(s.p99LatencyNs)}`} accent />
      <Stat label="Trades matched" value={s.tradeCount.toLocaleString('en-US')} sub="since start" />
    </div>
  );
}

function Stat({ label, value, sub, tone, accent }: { label: string; value: string; sub: string; tone?: 'good' | 'bad' | 'warn'; accent?: boolean }) {
  return (
    <div className={`xt-stat ${accent ? 'accent' : ''}`}>
      <span className="xts-label">{label}</span>
      <span className={`xts-value ${tone ?? ''}`}>{value}</span>
      <span className="xts-sub">{sub}</span>
    </div>
  );
}

// ── order book ────────────────────────────────────────────────────────────────────────────────
function OrderBook({ bids, asks, stats, traded }: { bids: ExLevel[]; asks: ExLevel[]; stats: ExStats; traded: Set<number> }) {
  const rows = 11;
  const showAsks = asks.slice(0, rows);
  const showBids = bids.slice(0, rows);
  const maxSize = Math.max(1e-9, ...showAsks.map((l) => l.size), ...showBids.map((l) => l.size));

  return (
    <div className="xt-book">
      <div className="xt-book-head">
        <h2>Order Book</h2>
        <div className="xt-book-cols"><span>Price</span><span>Size (BTC)</span><span>Orders</span></div>
      </div>
      <div className="xt-book-body">
        {showAsks.slice().reverse().map((l, i) => <BookRow key={`a${i}`} l={l} side="ask" maxSize={maxSize} flash={traded.has(l.price)} />)}
        <div className="xt-mid">
          <span className="xtm-side bid">{usd(Number(bids[0]?.price ?? stats.mid))}</span>
          <span className="xtm-spread">{stats.spreadBps == null ? '—' : `${stats.spreadBps.toFixed(1)} bps spread`}</span>
          <span className="xtm-side ask">{usd(Number(asks[0]?.price ?? stats.mid))}</span>
        </div>
        {showBids.map((l, i) => <BookRow key={`b${i}`} l={l} side="bid" maxSize={maxSize} flash={traded.has(l.price)} />)}
      </div>
      <div className="xt-book-foot">Depth bars ∝ size · <b>MM</b> = market-maker quote · <b>YOU</b> = your order · levels flash on a match</div>
    </div>
  );
}

function BookRow({ l, side, maxSize, flash }: { l: ExLevel; side: 'bid' | 'ask'; maxSize: number; flash: boolean }) {
  const w = Math.min(100, (l.size / maxSize) * 100);
  return (
    <div className={`xt-row ${side} ${flash ? 'flash' : ''} ${l.you ? 'you' : ''}`}>
      <div className={`xt-depth ${side}`} style={{ width: `${w}%` }} />
      <span className="xtr-price">{usd(l.price)}{l.mm && <span className="xtr-tag mm">MM</span>}{l.you && <span className="xtr-tag you">YOU</span>}</span>
      <span className="xtr-size">{btc(l.size)}</span>
      <span className="xtr-orders">{l.orders}</span>
    </div>
  );
}

// ── order entry ───────────────────────────────────────────────────────────────────────────────
function OrderEntry({ mid, onPlaced, myOrders, onCancel }: {
  mid: number; onPlaced: (o: MyOrder | null) => void; myOrders: MyOrder[]; onCancel: (id: number) => void;
}) {
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [type, setType] = useState<'LIMIT' | 'MARKET'>('LIMIT');
  const [price, setPrice] = useState('');
  const [size, setSize] = useState('0.05');
  const [postOnly, setPostOnly] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const submit = useCallback(async () => {
    const px = type === 'LIMIT' ? Number(price || mid) : undefined;
    try {
      const r = await api.placeExchangeOrder({ side, type, tif: 'GTC', postOnly, price: px, size: Number(size) });
      if (r.status === 'REJECTED') setResult(`Rejected — ${r.reason}`);
      else if (r.status === 'FILLED') setResult(`Filled ${btc(r.filledSize)} BTC across ${r.trades} fills`);
      else if (r.status === 'PARTIALLY_FILLED') setResult(`Filled ${btc(r.filledSize)} BTC, remainder cancelled`);
      else setResult(`Resting ${btc(r.restingSize)} BTC in the queue`);
      if (r.status === 'RESTING' && px != null) onPlaced({ id: r.orderId, side, price: px, size: Number(size) });
    } catch (e) {
      setResult(String(e));
    }
  }, [side, type, price, size, postOnly, mid, onPlaced]);

  return (
    <div className="xt-entry">
      <h2>Place Order</h2>
      <div className="xt-side-toggle">
        <button className={side === 'BUY' ? 'buy active' : ''} onClick={() => setSide('BUY')}>Buy</button>
        <button className={side === 'SELL' ? 'sell active' : ''} onClick={() => setSide('SELL')}>Sell</button>
      </div>
      <div className="xt-entry-row">
        <label>Type
          <select value={type} onChange={(e) => setType(e.target.value as 'LIMIT' | 'MARKET')}>
            <option value="LIMIT">Limit</option>
            <option value="MARKET">Market</option>
          </select>
        </label>
        <label>Size (BTC)<input value={size} onChange={(e) => setSize(e.target.value)} inputMode="decimal" /></label>
      </div>
      {type === 'LIMIT' && (
        <div className="xt-entry-row">
          <label>Price ($)<input value={price} onChange={(e) => setPrice(e.target.value)} placeholder={String(Math.round(mid))} inputMode="decimal" /></label>
          <label className="xt-po"><input type="checkbox" checked={postOnly} onChange={(e) => setPostOnly(e.target.checked)} /> post-only</label>
        </div>
      )}
      <button className={`xt-place ${side.toLowerCase()}`} onClick={submit}>{side} {type}</button>
      {result && <div className="xt-result">{result}</div>}

      {myOrders.length > 0 && (
        <div className="xt-myorders">
          <div className="xt-mo-head">Your resting orders</div>
          {myOrders.map((o) => (
            <div key={o.id} className="xt-mo-row">
              <span className={o.side === 'BUY' ? 'pos' : 'neg'}>{o.side}</span>
              <span className="mono">{btc(o.size)} @ {usd(o.price)}</span>
              <button onClick={() => onCancel(o.id)}>cancel</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── trade tape ────────────────────────────────────────────────────────────────────────────────
function Tape({ trades }: { trades: ExTrade[] }) {
  return (
    <div className="xt-tape">
      <h2>Order Flow <span className="xt-h-sub">— aggressor lifts / hits a resting quote</span></h2>
      <div className="xt-tape-body">
        {trades.length === 0 && <div className="empty sm">waiting for trades…</div>}
        {trades.map((t) => (
          <div key={t.seq} className={`xt-tape-row ${t.aggressor === 'BUY' ? 'buy' : 'sell'}`}>
            <span className="xtt-arrow">{t.aggressor === 'BUY' ? '▲' : '▼'}</span>
            <span className="xtt-price">{usd(t.price)}</span>
            <span className="xtt-size">{btc(t.size)}</span>
            <span className="xtt-parties">{t.taker}→{t.maker}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── top-of-book queue (price-time priority made visible) ────────────────────────────────────────
function Queue({ bidQueue, askQueue }: { bidQueue: ExQueueOrder[]; askQueue: ExQueueOrder[] }) {
  return (
    <div className="xt-queue">
      <div className="xt-queue-head">
        <h2>Top-of-Book Queue</h2>
        <span className="xt-h-sub">individual resting orders in <b>price-time priority</b> — front of the queue fills first</span>
      </div>
      <div className="xt-queue-body">
        <QueueSide label="Bids (front → back)" orders={bidQueue} side="bid" />
        <QueueSide label="Asks (front → back)" orders={askQueue} side="ask" />
      </div>
    </div>
  );
}

function QueueSide({ label, orders, side }: { label: string; orders: ExQueueOrder[]; side: 'bid' | 'ask' }) {
  return (
    <div className="xt-qside">
      <div className="xt-qlabel">{label}</div>
      <div className={`xt-qtokens ${side}`}>
        {orders.map((o) => (
          <span key={o.id} className={`xt-token ${o.owner.toLowerCase()}`} title={`${o.owner} · ${btc(o.size)} BTC @ ${usd(o.price)}`}>
            {o.owner === 'MM' ? 'MM' : o.owner === 'YOU' ? 'YOU' : '·'}
            <span className="xt-token-sz">{btc(o.size)}</span>
          </span>
        ))}
        {orders.length === 0 && <span className="empty sm">—</span>}
      </div>
    </div>
  );
}
