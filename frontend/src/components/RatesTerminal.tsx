import { useCallback, useRef, useState } from 'react';
import { api } from '../api/client';
import type { RaBook, RaCurve, RaDealer, RaRfq, RaAnalytics } from '../api/types';
import { useRatesStream } from '../hooks/useRatesStream';

// The Fixed-Income product's flagship: a live rates dealing desk. The real Treasury curve evolves,
// client RFQs are shopped across a dealer panel (best-ex, information leakage), our desk wins flow and
// builds a book, and the desk P&L is attributed to its drivers. Built to be read: the curve you can
// shock, the RFQ auction you can watch, the key-rate risk of the book, and the P&L breakdown.

const UNIVERSE = ['UST 2Y', 'UST 5Y', 'UST 10Y', 'UST 30Y', "AAPL 4⅝ '30", "F 6.1 '32"];
const usd0 = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(Math.round(n)).toLocaleString('en-US');
const px = (n: number) => n.toFixed(3);

export function RatesTerminal() {
  const { connected, snapshot } = useRatesStream();
  const [manualRfq, setManualRfq] = useState<RaRfq | null>(null);

  return (
    <div className="rt">
      <div className="rt-intro">
        <span className={`dot ${connected ? 'live' : 'down'}`} />
        A live <b>rates dealing desk</b> — the real Treasury curve, client RFQs shopped across a dealer
        panel with best-execution and information leakage, our book, and its P&amp;L attribution.
      </div>
      {!snapshot ? (
        <div className="rt-loading">connecting to the rates desk…</div>
      ) : (
        <>
          <div className="rt-row">
            <CurvePanel curve={snapshot.curve} />
            <RfqPanel rfq={manualRfq ?? snapshot.lastRfq} manual={manualRfq != null} onSubmit={setManualRfq} />
          </div>
          <div className="rt-row">
            <BookPanel book={snapshot.book} />
            <PnlPanel book={snapshot.book} />
          </div>
          <div className="rt-row">
            <AnalyticsPanel a={snapshot.analytics} />
            <DealerPanel dealers={snapshot.dealers} />
          </div>
        </>
      )}
    </div>
  );
}

// ── yield curve (shockable) ──────────────────────────────────────────────────────────────────────
function CurvePanel({ curve }: { curve: RaCurve }) {
  const [parallel, setParallel] = useState(curve.parallelShockBps);
  const [slope, setSlope] = useState(curve.slopeShockBps);
  const timer = useRef<number | undefined>(undefined);

  const shock = useCallback((p: number, s: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { void api.ratesShock({ parallelBps: p, slopeBps: s }).catch(() => {}); }, 120);
  }, []);

  const W = 520, H = 200, m = { l: 40, r: 14, t: 14, b: 28 };
  const t = curve.tenors, y = curve.parYields;
  const ymin = Math.min(...y) - 0.2, ymax = Math.max(...y) + 0.2;
  const xi = (i: number) => m.l + (i / (t.length - 1)) * (W - m.l - m.r);
  const yc = (v: number) => m.t + (1 - (v - ymin) / (ymax - ymin)) * (H - m.t - m.b);
  const line = y.map((v, i) => `${xi(i).toFixed(1)},${yc(v).toFixed(1)}`).join(' ');
  const ticks = [ymin, (ymin + ymax) / 2, ymax];
  const labelIdx = [0, 3, 5, 7, 9, 11, 13].filter((i) => i < t.length);

  return (
    <div className="rt-card rt-curve">
      <div className="rt-head"><h2>US Treasury Curve</h2><span className="rt-sub">as of {curve.asOf} · live + your shock</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} className="rt-curve-svg">
        {ticks.map((v, k) => (
          <g key={k}>
            <line x1={m.l} x2={W - m.r} y1={yc(v)} y2={yc(v)} className="rt-grid" />
            <text x={m.l - 5} y={yc(v) + 3} textAnchor="end" className="rt-axis">{v.toFixed(1)}%</text>
          </g>
        ))}
        {labelIdx.map((i) => (
          <text key={i} x={xi(i)} y={H - 8} textAnchor="middle" className="rt-axis">{t[i] < 1 ? `${Math.round(t[i] * 12)}m` : `${t[i]}y`}</text>
        ))}
        <polyline points={line} className="rt-curve-line" />
        {y.map((v, i) => <circle key={i} cx={xi(i)} cy={yc(v)} r={2} className="rt-curve-dot" />)}
      </svg>
      <div className="rt-shock">
        <label>Parallel shock <b>{parallel >= 0 ? '+' : ''}{parallel}bp</b>
          <input type="range" min={-100} max={100} step={5} value={parallel} onChange={(e) => { const v = Number(e.target.value); setParallel(v); shock(v, slope); }} />
        </label>
        <label>Slope (2s30s) <b>{slope >= 0 ? '+' : ''}{slope}bp</b>
          <input type="range" min={-60} max={60} step={5} value={slope} onChange={(e) => { const v = Number(e.target.value); setSlope(v); shock(parallel, v); }} />
        </label>
        <button className="rt-reset" onClick={() => { setParallel(0); setSlope(0); shock(0, 0); }}>reset</button>
      </div>
    </div>
  );
}

// ── RFQ auction (watchable) ──────────────────────────────────────────────────────────────────────
function RfqPanel({ rfq, manual, onSubmit }: { rfq: RaRfq | null; manual: boolean; onSubmit: (r: RaRfq | null) => void }) {
  const [inst, setInst] = useState(UNIVERSE[2]);
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [size, setSize] = useState(10);
  const [n, setN] = useState(5);

  const submit = useCallback(async () => {
    try { onSubmit(await api.ratesSubmitRfq({ instrument: inst, side, sizeMM: size, nDealers: n })); } catch { /* */ }
  }, [inst, side, size, n, onSubmit]);

  return (
    <div className="rt-card rt-rfq">
      <div className="rt-head"><h2>Dealer RFQ Auction</h2><span className="rt-sub">shop an order · best-ex · leakage</span></div>
      <div className="rt-rfq-form">
        <select value={inst} onChange={(e) => setInst(e.target.value)}>{UNIVERSE.map((u) => <option key={u}>{u}</option>)}</select>
        <div className="rt-sidetoggle">
          <button className={side === 'BUY' ? 'buy on' : ''} onClick={() => setSide('BUY')}>Buy</button>
          <button className={side === 'SELL' ? 'sell on' : ''} onClick={() => setSide('SELL')}>Sell</button>
        </div>
        <label>${size}mm<input type="range" min={1} max={30} value={size} onChange={(e) => setSize(Number(e.target.value))} /></label>
        <label>{n} dealers<input type="range" min={1} max={8} value={n} onChange={(e) => setN(Number(e.target.value))} /></label>
        <button className="rt-send" onClick={submit}>Request</button>
      </div>
      {rfq && (
        <div className="rt-auction">
          <div className="rt-auction-head">
            <span className={rfq.side === 'BUY' ? 'buy' : 'sell'}>{rfq.side} ${rfq.sizeMM}mm {rfq.instrument}</span>
            <span className="rt-mid">mid {px(rfq.compositeMid)} · leak {rfq.leakagePx.toFixed(3)} · <b>{rfq.costBps.toFixed(2)}bps</b>{manual && <span className="rt-manual">yours</span>}</span>
          </div>
          <div className="rt-quotes">
            {rfq.quotes.map((q, i) => (
              <div key={i} className={`rt-quote ${q.best ? 'best' : ''} ${q.us ? 'us' : ''}`}>
                <span className="rt-q-name">{q.name}{q.us && <span className="rt-tag us">US</span>}{q.best && <span className="rt-tag best">WON</span>}</span>
                <span className="rt-q-px">{px(q.price)}</span>
                <span className="rt-q-bps">{q.fromMidBps >= 0 ? '+' : ''}{q.fromMidBps.toFixed(2)}bps</span>
              </div>
            ))}
          </div>
          <div className="rt-auction-foot">Best-ex: <b>{rfq.winner}</b> @ {px(rfq.executedPrice)} · saved {rfq.competitionPx.toFixed(3)} vs 2nd</div>
        </div>
      )}
    </div>
  );
}

// ── book + key-rate risk ─────────────────────────────────────────────────────────────────────────
function BookPanel({ book }: { book: RaBook }) {
  const kr = book.keyRateDv01;
  const maxAbs = Math.max(1, ...kr.map((k) => Math.abs(k.dv01Usd)));
  return (
    <div className="rt-card rt-book">
      <div className="rt-head"><h2>Our Book &amp; Key-Rate Risk</h2><span className="rt-sub">net DV01 {usd0(book.dv01Usd)}/bp · value {usd0(book.valueUsd)}</span></div>
      <div className="rt-book-body">
        <div className="rt-kr">
          <div className="rt-kr-title">Key-rate DV01 — $ per 1bp, by curve pillar (where the risk sits)</div>
          {kr.map((k) => (
            <div key={k.tenor} className="rt-kr-row">
              <span className="rt-kr-tenor">{k.tenor < 1 ? `${Math.round(k.tenor * 12)}m` : `${k.tenor}y`}</span>
              <div className="rt-kr-bar-wrap">
                <div className="rt-kr-zero" />
                <div className={`rt-kr-bar ${k.dv01Usd >= 0 ? 'pos' : 'neg'}`}
                  style={{ width: `${(Math.abs(k.dv01Usd) / maxAbs) * 50}%`, [k.dv01Usd >= 0 ? 'left' : 'right']: '50%' } as React.CSSProperties} />
              </div>
              <span className={`rt-kr-val ${k.dv01Usd >= 0 ? 'pos' : 'neg'}`}>{usd0(k.dv01Usd)}</span>
            </div>
          ))}
          {kr.length === 0 && <div className="rt-empty">no positions yet — the desk is warming up</div>}
        </div>
        <div className="rt-positions">
          <table>
            <thead><tr><th>Position</th><th className="r">$mm</th><th className="r">Px</th><th className="r">DV01</th></tr></thead>
            <tbody>
              {book.positions.map((p) => (
                <tr key={p.instrument}>
                  <td>{p.instrument}</td>
                  <td className={`r ${p.positionMM >= 0 ? 'pos' : 'neg'}`}>{p.positionMM >= 0 ? '+' : ''}{p.positionMM}</td>
                  <td className="r dim">{px(p.price)}</td>
                  <td className="r">{usd0(p.dv01Usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── P&L attribution ──────────────────────────────────────────────────────────────────────────────
function PnlPanel({ book }: { book: RaBook }) {
  const p = book.pnl;
  const rows = [
    { k: 'Trading (spread captured)', v: p.trading },
    { k: 'Carry', v: p.carry },
    { k: 'Rates — parallel', v: p.rateParallel },
    { k: 'Rates — reshaping', v: p.rateReshape },
    { k: 'Credit spread', v: p.credit },
  ];
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.v)));
  return (
    <div className="rt-card rt-pnl">
      <div className="rt-head"><h2>Desk P&amp;L Attribution</h2><span className="rt-sub">total <b className={p.totalUsd >= 0 ? 'pos' : 'neg'}>{usd0(p.totalUsd)}</b></span></div>
      <div className="rt-pnl-body">
        {rows.map((r) => (
          <div key={r.k} className="rt-pnl-row">
            <span className="rt-pnl-k">{r.k}</span>
            <div className="rt-pnl-bar-wrap">
              <div className="rt-kr-zero" />
              <div className={`rt-pnl-bar ${r.v >= 0 ? 'pos' : 'neg'}`} style={{ width: `${(Math.abs(r.v) / max) * 50}%`, [r.v >= 0 ? 'left' : 'right']: '50%' } as React.CSSProperties} />
            </div>
            <span className={`rt-pnl-v ${r.v >= 0 ? 'pos' : 'neg'}`}>{usd0(r.v)}</span>
          </div>
        ))}
      </div>
      <div className="rt-pnl-note">Spread captured on the RFQs we win, less what the curve (parallel + reshaping) and credit move against the book, plus carry.</div>
    </div>
  );
}

// ── RFQ analytics (leakage curve) ────────────────────────────────────────────────────────────────
function AnalyticsPanel({ a }: { a: RaAnalytics }) {
  const maxCost = Math.max(0.1, ...a.leakageCurve.map((l) => l.avgCostBps));
  return (
    <div className="rt-card rt-an">
      <div className="rt-head"><h2>RFQ Analytics</h2><span className="rt-sub">win rate {a.winRatePct}% · {a.totalRfqs} RFQs · avg cost {a.avgCostBps}bps</span></div>
      <div className="rt-an-title">Execution cost by number of dealers shopped — competition tightens it, but leakage bites</div>
      <div className="rt-leak">
        {a.leakageCurve.map((l) => (
          <div key={l.dealers} className="rt-leak-row">
            <span className="rt-leak-n">{l.dealers} dlrs</span>
            <div className="rt-leak-bar-wrap"><div className="rt-leak-bar" style={{ width: `${(l.avgCostBps / maxCost) * 100}%` }} /></div>
            <span className="rt-leak-cost">{l.avgCostBps.toFixed(2)}bps</span>
            <span className="rt-leak-leak">leak {l.avgLeakagePx.toFixed(3)}</span>
          </div>
        ))}
        {a.leakageCurve.length === 0 && <div className="rt-empty">warming up…</div>}
      </div>
    </div>
  );
}

// ── dealer panel ─────────────────────────────────────────────────────────────────────────────────
function DealerPanel({ dealers }: { dealers: RaDealer[] }) {
  const maxInv = Math.max(1, ...dealers.map((d) => Math.abs(d.inventory)));
  return (
    <div className="rt-card rt-dealers">
      <div className="rt-head"><h2>Dealer Panel</h2><span className="rt-sub">inventory / axe ($mm) — drives each dealer's skew</span></div>
      <div className="rt-dealer-list">
        {dealers.map((d) => (
          <div key={d.name} className={`rt-dealer ${d.us ? 'us' : ''}`}>
            <span className="rt-dealer-name">{d.name}{d.us && <span className="rt-tag us">US</span>}</span>
            <div className="rt-kr-bar-wrap">
              <div className="rt-kr-zero" />
              <div className={`rt-kr-bar ${d.inventory >= 0 ? 'pos' : 'neg'}`} style={{ width: `${(Math.abs(d.inventory) / maxInv) * 50}%`, [d.inventory >= 0 ? 'left' : 'right']: '50%' } as React.CSSProperties} />
            </div>
            <span className={`rt-dealer-inv ${d.inventory >= 0 ? 'pos' : 'neg'}`}>{d.inventory >= 0 ? '+' : ''}{d.inventory}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
