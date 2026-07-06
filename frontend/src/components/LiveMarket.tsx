import { useCallback, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { PaperOrder } from '../api/types';
import { usePolling } from '../hooks/usePolling';

const PRODUCTS = ['BTC-USD', 'ETH-USD', 'SOL-USD'];

const usd = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
const sz = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 6 });

export function LiveMarket() {
  const [product, setProduct] = useState('BTC-USD');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [type, setType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [size, setSize] = useState('0.5');
  const [limit, setLimit] = useState('');
  const [result, setResult] = useState<PaperOrder | null>(null);

  const book = usePolling(useCallback(() => api.marketBook(product, 12), [product]), 800);
  const quotes = usePolling(api.marketProducts, 1000);
  const trades = usePolling(useCallback(() => api.marketTrades(product), [product]), 1500);
  const positions = usePolling(api.cryptoPositions, 2000);

  const live = book.error == null;
  const quote = book.data?.quote;

  const maxCum = useMemo(() => {
    const b = book.data;
    if (!b) return 1;
    const all = [...b.bids, ...b.asks].map((l) => l.cumulative);
    return Math.max(1, ...all);
  }, [book.data]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const order = await api.submitPaperOrder(product, {
      side,
      type,
      size: Number(size),
      limitPrice: type === 'LIMIT' && limit ? Number(limit) : null,
    });
    setResult(order);
    positions.refresh();
  }

  const bannerKind = (s: string) => (s === 'FILLED' ? 'ok' : s === 'PARTIALLY_FILLED' ? 'warn' : 'err');

  return (
    <div className="risk">
      <div className="market-head">
        <div className="product-tabs">
          {PRODUCTS.map((p) => (
            <button key={p} className={p === product ? 'active' : ''} onClick={() => setProduct(p)}>
              {p}
            </button>
          ))}
        </div>
        <div className="quote-strip">
          {quotes.data
            ?.filter((q) => PRODUCTS.includes(q.product))
            .map((q) => (
              <span key={q.product} className={q.product === product ? 'q active' : 'q'}>
                <b>{q.product.replace('-USD', '')}</b> {usd(q.lastPrice)}
              </span>
            ))}
        </div>
      </div>

      <div className="market-grid">
        {/* ---- Depth ladder ---- */}
        <div className="panel">
          <div className="panel-head">
            <h2>{product} Order Book</h2>
            <span className="count">
              {quote ? `spread ${usd(quote.spread)} (${quote.spreadBps ?? '—'} bps)` : 'connecting…'}
            </span>
          </div>
          <div className="ladder">
            {book.data?.asks
              .slice()
              .reverse()
              .map((l) => (
                <div className="lvl ask" key={`a${l.price}`}>
                  <div className="depthbar ask" style={{ width: `${(l.cumulative / maxCum) * 100}%` }} />
                  <span className="lp sell">{usd(l.price)}</span>
                  <span className="lsz">{sz(l.size)}</span>
                </div>
              ))}
            <div className="ladder-mid">
              {quote?.mid != null ? usd(quote.mid) : '—'} <span className="dim">mid</span>
            </div>
            {book.data?.bids.map((l) => (
              <div className="lvl bid" key={`b${l.price}`}>
                <div className="depthbar bid" style={{ width: `${(l.cumulative / maxCum) * 100}%` }} />
                <span className="lp buy">{usd(l.price)}</span>
                <span className="lsz">{sz(l.size)}</span>
              </div>
            ))}
            {!book.data && <div className="empty">Waiting for live feed…</div>}
          </div>
        </div>

        {/* ---- Order ticket + tape ---- */}
        <div className="market-side">
          <form className="ticket" onSubmit={submit}>
            <h2>Paper Trade · {product}</h2>
            <div className="segmented">
              {(['BUY', 'SELL'] as const).map((s) => (
                <button type="button" key={s} className={`seg ${side === s ? 'active ' + s.toLowerCase() : ''}`}
                        onClick={() => setSide(s)}>
                  {s}
                </button>
              ))}
            </div>
            <div className="row">
              <label>
                Type
                <select value={type} onChange={(e) => setType(e.target.value as 'MARKET' | 'LIMIT')}>
                  <option>MARKET</option>
                  <option>LIMIT</option>
                </select>
              </label>
              <label>
                Size
                <input type="number" step="0.0001" min="0" value={size} onChange={(e) => setSize(e.target.value)} />
              </label>
              {type === 'LIMIT' && (
                <label>
                  Limit
                  <input type="number" step="0.01" value={limit} onChange={(e) => setLimit(e.target.value)} />
                </label>
              )}
            </div>
            <button className="submit" type="submit" disabled={!live || !size}>
              {side} {product}
            </button>
            {result && (
              <div className={`banner ${bannerKind(result.status)}`}>
                {result.status} · filled {sz(result.filledSize)} @ {usd(result.avgPrice)} · {result.notional && usd(result.notional)} ·
                slippage {result.slippageBps} bps across {result.fills.length} levels
              </div>
            )}
          </form>

          <div className="panel tape">
            <div className="panel-head">
              <h2>Trade Tape</h2>
              <span className="count">live</span>
            </div>
            <div className="tape-body">
              {(trades.data ?? []).slice(0, 14).map((t, i) => (
                <div className={`tprint ${t.side.toLowerCase() === 'buy' ? 'buy' : 'sell'}`} key={i}>
                  <span>{t.side.toUpperCase()}</span>
                  <span className="mono">{sz(t.size)}</span>
                  <span className="mono">{usd(t.price)}</span>
                  <span className="dim">{t.time.slice(11, 19)}</span>
                </div>
              ))}
              {(trades.data ?? []).length === 0 && <div className="empty">Waiting for trades…</div>}
            </div>
          </div>
        </div>
      </div>

      {/* ---- Positions ---- */}
      <div className="panel">
        <div className="panel-head">
          <h2>Crypto Positions</h2>
          <span className="count">live mark-to-market</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th className="num">Net Size</th>
                <th className="num">Avg Cost</th>
                <th className="num">Mark</th>
                <th className="num">Market Value</th>
                <th className="num">Unrealized P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {(positions.data ?? []).length === 0 && (
                <tr><td colSpan={6} className="empty">No positions — paper-trade against the live book above.</td></tr>
              )}
              {(positions.data ?? []).map((p) => (
                <tr key={p.product}>
                  <td className="sec">{p.product}</td>
                  <td className={`num mono ${p.netSize < 0 ? 'sell' : 'buy'}`}>{sz(p.netSize)}</td>
                  <td className="num mono">{usd(p.avgCost)}</td>
                  <td className="num mono">{usd(p.markPrice)}</td>
                  <td className="num mono">{usd(p.marketValue)}</td>
                  <td className={`num mono ${(p.unrealizedPnl ?? 0) >= 0 ? 'buy' : 'sell'}`}>{usd(p.unrealizedPnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
