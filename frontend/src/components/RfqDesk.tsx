import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { OrderSide, Rfq, RfqExecution, Security } from '../api/types';

// The fixed-income OTC desk, made legible. Bonds don't trade on a lit book — you request a quote and
// a panel of dealers price it off the benchmark curve. This surface shows the whole auction: the
// pricing math (fair yield = curve + credit spread), the dealer quotes arriving, best-execution
// highlighted, and the accepted trade booked into the blotter. No black box.

const TRADER = 'demo-trader';
const num = (n: number) => n.toLocaleString('en-US');
const price = (n: number | null) => (n == null ? '—' : n.toFixed(3));
const pct = (n: number | null) => (n == null ? '—' : n.toFixed(3) + '%');
const bps = (n: number | null) => (n == null ? '—' : Math.round(n) + ' bps');

export function RfqDesk({ bonds, portfolio, onBooked }: { bonds: Security[]; portfolio: string; onBooked: () => void }) {
  const [cusip, setCusip] = useState('');
  const [side, setSide] = useState<OrderSide>('BUY');
  const [qty, setQty] = useState(1_000_000);
  const [rfq, setRfq] = useState<Rfq | null>(null);
  const [revealed, setRevealed] = useState(0);
  const [exec, setExec] = useState<RfqExecution | null>(null);
  const [recent, setRecent] = useState<Rfq[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!cusip && bonds.length) setCusip(bonds[0].cusip);
  }, [bonds, cusip]);

  const loadRecent = useCallback(() => { api.rfqList().then(setRecent).catch(() => {}); }, []);
  useEffect(() => { loadRecent(); }, [loadRecent]);

  // Reveal dealer quotes one at a time so the auction feels live (they arrive over ~1.5s).
  useEffect(() => {
    if (!rfq) return;
    setRevealed(0);
    const id = window.setInterval(() => {
      setRevealed((r) => {
        if (r >= rfq.quotes.length) { window.clearInterval(id); return r; }
        return r + 1;
      });
    }, 320);
    return () => window.clearInterval(id);
  }, [rfq]);

  const request = useCallback(async () => {
    if (!cusip) return;
    setBusy(true);
    setErr(null);
    setExec(null);
    try {
      const r = await api.rfqCreate({ cusip, portfolio, trader: TRADER, side, quantity: qty });
      setRfq(r);
      loadRecent();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }, [cusip, side, qty, portfolio, loadRecent]);

  const accept = useCallback(async (dealer?: string) => {
    if (!rfq) return;
    setBusy(true);
    setErr(null);
    try {
      const x = await api.rfqAccept(rfq.id, dealer);
      setExec(x);
      const updated = await api.rfqGet(rfq.id).catch(() => null);
      if (updated) setRfq(updated);
      onBooked();
      loadRecent();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }, [rfq, onBooked, loadRecent]);

  const allRevealed = rfq ? revealed >= rfq.quotes.length : false;
  const done = rfq?.status === 'FILLED' || exec != null;

  return (
    <div className="panel rfq-desk">
      <div className="panel-head">
        <h2>RFQ Desk — OTC Dealer Auction</h2>
        <span className="count">request → quote → best-ex → book</span>
      </div>

      <div className="rfq-form">
        <label className="rfq-field">
          <span>Bond</span>
          <select value={cusip} onChange={(e) => setCusip(e.target.value)}>
            {bonds.map((b) => (
              <option key={b.cusip} value={b.cusip}>{b.description}</option>
            ))}
          </select>
        </label>
        <label className="rfq-field side">
          <span>Side</span>
          <div className="side-toggle">
            <button className={side === 'BUY' ? 'buy active' : ''} onClick={() => setSide('BUY')}>Buy</button>
            <button className={side === 'SELL' ? 'sell active' : ''} onClick={() => setSide('SELL')}>Sell</button>
          </div>
        </label>
        <label className="rfq-field">
          <span>Face ($)</span>
          <input type="number" min={1000} step={1000} value={qty} onChange={(e) => setQty(Number(e.target.value))} />
        </label>
        <button className="rfq-request" disabled={busy || !cusip} onClick={request}>
          {busy ? 'Requesting…' : 'Request Quotes'}
        </button>
      </div>

      {err && <div className="rfq-err">{err}</div>}

      {rfq && (
        <div className="rfq-live">
          {/* Pricing math — the thing that de-black-boxes the OTC price */}
          <div className="rfq-math">
            <span className="rm-step"><b>{rfq.side}</b> ${num(rfq.quantity)} · {rfq.description}</span>
            <span className="rm-arrow">→</span>
            <span className="rm-step">benchmark {rfq.tenorYears?.toFixed(1)}y <b>{pct(rfq.curveYieldPct)}</b></span>
            <span className="rm-arrow">+</span>
            <span className="rm-step">credit <b>{bps(rfq.creditSpreadBps)}</b></span>
            <span className="rm-arrow">=</span>
            <span className="rm-step">fair yield <b>{pct(rfq.fairYieldPct)}</b></span>
            <span className="rm-arrow">→</span>
            <span className="rm-step accent">fair clean <b>{price(rfq.fairClean)}</b></span>
          </div>

          {/* Dealer quotes, revealed one by one */}
          <div className="rfq-quotes">
            <div className="rq-head">
              <span>Dealer</span><span className="r">Price</span><span className="r">Yield</span>
              <span className="r">Spread</span><span className="r">Size</span><span className="r"></span>
            </div>
            {rfq.quotes.slice(0, revealed).map((q) => (
              <div key={q.dealer} className={`rq-row ${q.best ? 'best' : ''} ${exec?.dealer === q.dealer ? 'accepted' : ''}`}>
                <span className="rq-dealer">{q.dealer}{q.best && <span className="best-tag">best-ex</span>}</span>
                <span className="r mono">{price(q.price)}</span>
                <span className="r mono dim">{pct(q.yieldPct)}</span>
                <span className="r mono dim">{bps(q.spreadBps)}</span>
                <span className="r mono dim">${num(q.size)}</span>
                <span className="r">
                  {!done && <button className="rq-accept" disabled={busy} onClick={() => accept(q.dealer)}>Lift</button>}
                </span>
              </div>
            ))}
            {!allRevealed && <div className="rq-pending">dealers responding…</div>}
          </div>

          {allRevealed && !done && (
            <button className="rfq-bestex" disabled={busy} onClick={() => accept()}>
              Accept best execution
            </button>
          )}

          {exec && (
            <div className="rfq-booked">
              <span className="rb-check">✓ Booked</span>
              <span>
                {exec.side} ${num(exec.quantity ?? 0)} @ <b>{price(exec.price)}</b> with <b>{exec.dealer}</b>{' '}
                → order <b>{exec.orderRef}</b> ({exec.status}) · now in the blotter below
              </span>
            </div>
          )}
        </div>
      )}

      {recent.length > 0 && (
        <div className="rfq-recent">
          <div className="rr-head">Recent RFQs</div>
          {recent.slice(0, 6).map((r) => (
            <div key={r.id} className="rr-row">
              <span className="rr-desc">{r.side} {r.description}</span>
              <span className="mono dim">${num(r.quantity)}</span>
              <span className={`rr-status ${r.status.toLowerCase()}`}>{r.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
