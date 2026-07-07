import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type {
  BacktestResult, Construction, Findings, MicroDecayPoint, MicroStudy, MicroSweepPoint, SignalMeta,
} from '../api/types';
import { Callout, Chapter, EquityChart, MetricCtx } from './ui';

// The Research Lab — the project's focal point, told as a guided story a reviewer can follow in two
// minutes: (1) single factors fail the honest statistical gauntlet, (2) so the edge is portfolio
// construction, (3) run any factor yourself through the same pipeline. This surface is the reference
// standard for the whole site: clear hierarchy, labeled charts, and every number explained.

const sh = (n: number | null | undefined) => (n == null ? '—' : (n >= 0 ? '+' : '') + n.toFixed(2));
const pct = (n: number | null | undefined) => (n == null ? '—' : (n * 100).toFixed(1) + '%');
const num = (n: number | null | undefined, d = 2) => (n == null ? '—' : n.toFixed(d));
const money = (n: number | null | undefined) =>
  n == null ? '—' : (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });

export function ResearchLab() {
  const [signals, setSignals] = useState<SignalMeta[]>([]);
  const [findings, setFindings] = useState<Findings | null>(null);
  const [construction, setConstruction] = useState<Construction | null>(null);
  const [down, setDown] = useState(false);

  const [signal, setSignal] = useState('composite');
  const [costBps, setCostBps] = useState(5);
  const [neutralize, setNeutralize] = useState(true);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.researchSignals().then(setSignals).catch(() => setDown(true));
    api.researchFindings().then(setFindings).catch(() => setDown(true));
    api.researchConstruction().then(setConstruction).catch(() => {});
  }, []);

  const run = useCallback(async () => {
    setRunning(true);
    try {
      setResult(await api.researchBacktest(signal, costBps, neutralize));
      setDown(false);
    } catch {
      setDown(true);
    } finally {
      setRunning(false);
    }
  }, [signal, costBps, neutralize]);

  useEffect(() => { void run(); /* eslint-disable-next-line */ }, []);

  if (down && !findings && !result) {
    return (
      <div className="guide">
        <div className="banner err global">
          The research service isn't reachable at <code>/research-api</code>. Start it from{' '}
          <code>research/</code>: <code>uvicorn service.app:app --port 8082</code> (or bring up the Docker stack).
        </div>
      </div>
    );
  }

  const u = findings?.universe;
  const sel = findings?.selection;

  return (
    <div className="guide">
      {/* ---- framing hero ---- */}
      <header className="guide-hero">
        <span className="guide-eyebrow">Quant Research</span>
        <h1 className="guide-title">Is there alpha in mega-cap equities?</h1>
        <p className="guide-sub">
          A rigorous, self-critical research pipeline. Every candidate signal is backtested as a
          dollar-neutral, cost-aware, walk-forward book and forced through the same overfitting
          gauntlet — so the answer below is honest, not a cherry-picked backtest.
        </p>
        {u && (
          <div className="guide-chips">
            <span className="gchip"><b>{u.names}</b> mega-cap names</span>
            <span className="gchip"><b>{(u.days / 252).toFixed(1)}y</b> ({u.start} → {u.end})</span>
            <span className="gchip">net of costs</span>
            <span className="gchip">walk-forward · no look-ahead</span>
          </div>
        )}
      </header>

      {/* ---- chapter 1: the honest null ---- */}
      <Chapter
        num="01 — The Honest Null"
        title="No single factor survives"
        lede={<>We tested {findings?.signals.length ?? 18} classic equity factors — value, momentum, quality,
          low-risk and more. To count as <b>real</b> (not luck, not overfitting), a factor must clear all
          three of these checks at once:</>}
      >
        <div className="gauntlet">
          <div className="gcheck">
            <div className="gcheck-name">Newey–West t-stat</div>
            <div className="gcheck-q">Is the return distinguishable from zero, once you stop pretending it's noise-free (autocorrelation-adjusted)?</div>
            <div className="gcheck-bar">Pass: <b>|t| &gt; {num(sel?.bonferroni_z)}</b> — the bar, raised for testing {sel?.n_trials ?? 18} factors at once.</div>
          </div>
          <div className="gcheck">
            <div className="gcheck-name">Deflated Sharpe</div>
            <div className="gcheck-q">After trying many strategies, what's the probability this one's edge is genuinely positive?</div>
            <div className="gcheck-bar">Pass: <b>&gt; 0.95</b>.</div>
          </div>
          <div className="gcheck">
            <div className="gcheck-name">PBO</div>
            <div className="gcheck-q">How often does the best in-sample factor turn into a loser out-of-sample (probability of backtest overfitting)?</div>
            <div className="gcheck-bar">Good: <b>&lt; 0.5</b>.</div>
          </div>
        </div>

        {findings && (
          <div className="panel">
            <div className="panel-head">
              <h2>Every factor, one verdict</h2>
              <span className="count">neutralized · net of 5bps cost</span>
            </div>
            <div className="tablewrap">
              <table className="data-table">
                <thead>
                  <tr><th>Factor</th><th>Family</th><th className="r">Net Sharpe</th><th className="r">t-stat</th><th className="r">Verdict</th></tr>
                </thead>
                <tbody>
                  {findings.signals.slice(0, 8).map((r) => (
                    <tr key={r.name}>
                      <td>{r.label}</td>
                      <td className="dim">{r.family}</td>
                      <td className={`r mono ${(r.net_sharpe ?? 0) >= 0 ? 'pos' : 'neg'}`}>{sh(r.net_sharpe)}</td>
                      <td className="r mono dim">{sh(r.hac_t)}</td>
                      <td className="r">{r.significant ? <span className="tag-sig">passes</span> : <span className="tag-no">not significant</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {findings.signals.length > 8 && (
              <div className="lab-note" style={{ borderRadius: 0 }}>…and {findings.signals.length - 8} more — all below the bar.</div>
            )}
          </div>
        )}

        {sel && (
          <Callout figure={`DSR ${num(sel.deflated_sharpe)}`} tone="warn">
            <b>Not one of {sel.n_trials} factors clears the bar.</b> The best factor's Deflated Sharpe is{' '}
            {num(sel.deflated_sharpe)} — it needs 0.95. This isn't a failure of technique (the pipeline is
            deliberately rigorous); it's the efficient-market ceiling on the easiest names with the weakest data.
          </Callout>
        )}
      </Chapter>

      {/* ---- chapter 2: construction is the edge ---- */}
      {construction && <ConstructionChapter c={construction} />}

      {/* ---- chapter 3: microstructure — where the signal actually is ---- */}
      <MicrostructureChapter />

      {/* ---- chapter 4: run it yourself ---- */}
      <Chapter
        num="04 — Run It Yourself"
        title="The same pipeline, on demand"
        lede={<>Pick any factor (or the composite), set the cost assumption, and it runs through the exact
          honest backtest above — the equity curve and the statistics update live. Nothing is pre-baked.</>}
      >
        <div className="lab2">
          <div className="lab2-controls">
            <label className="lab2-field">
              <span>Factor</span>
              <select value={signal} onChange={(e) => setSignal(e.target.value)}>
                {signals.map((s) => <option key={s.name} value={s.name}>{s.label}</option>)}
              </select>
            </label>
            <label className="lab2-field">
              <span>Trading cost: {costBps} bps per turnover</span>
              <input type="range" min={0} max={30} step={1} value={costBps} onChange={(e) => setCostBps(Number(e.target.value))} />
            </label>
            <label className="lab2-toggle">
              <input type="checkbox" checked={neutralize} onChange={(e) => setNeutralize(e.target.checked)} />
              β + sector neutralize (the investable book)
            </label>
            <button className="btn primary" onClick={run} disabled={running}>
              {running ? 'Running…' : 'Run backtest'}
            </button>
            {result && (
              <p className="mctx-ctx" style={{ marginTop: '-4px' }}>
                {result.label} · {result.days} trading days · turnover {num(result.avg_turnover)}/day
              </p>
            )}
          </div>

          {result && (
            <div className="lab2-result">
              <div className="lab2-chart-head">
                <h4>Growth of $1 — net of cost, walk-forward</h4>
                <span className="lab2-final" style={{ color: (result.net_sharpe ?? 0) >= 0 ? 'var(--buy)' : 'var(--sell)' }}>
                  ×{result.equity_curve.length ? result.equity_curve[result.equity_curve.length - 1].value.toFixed(2) : '—'}
                </span>
              </div>
              <EquityChart curve={result.equity_curve} up={(result.net_sharpe ?? 0) >= 0} />

              <div className="lab2-stats">
                <MetricCtx label="Net Sharpe" value={sh(result.net_sharpe)} tone={(result.net_sharpe ?? 0) >= 0 ? 'good' : 'bad'}
                  ctx="annualized return per unit risk, after cost · 1.0+ is strong" />
                <MetricCtx label="t-stat (HAC)" value={sh(result.hac_t)}
                  ctx={`significance, autocorr-adjusted · |t| > ${num(result.bonferroni_z)} to pass`} />
                <MetricCtx label="95% CI (Sharpe)" value={`${sh(result.boot_lo)}…${sh(result.boot_hi)}`}
                  ctx="bootstrap range — spans 0 = not distinguishable" />
                <MetricCtx label="Ann. return" value={pct(result.ann_return)} tone={(result.ann_return ?? 0) >= 0 ? 'good' : 'bad'}
                  ctx="annualized, net of cost" />
                <MetricCtx label="Max drawdown" value={pct(result.max_drawdown)} tone="bad"
                  ctx="worst peak-to-trough loss" />
                <MetricCtx label="Turnover" value={num(result.avg_turnover)}
                  ctx="fraction of the book traded per day · lower = cheaper" />
              </div>

              <div className={`lab2-verdict ${result.significant ? (result.net_sharpe && result.net_sharpe > 0 ? 'good' : 'warn') : 'neutral'}`}>
                <span className="lab2-chip">
                  {result.significant ? (result.net_sharpe && result.net_sharpe > 0 ? 'CANDIDATE' : 'SIGNIFICANT LOSER') : 'NOT SIGNIFICANT'}
                </span>
                {result.verdict}
              </div>
            </div>
          )}
        </div>
      </Chapter>
    </div>
  );
}

function ConstructionChapter({ c }: { c: Construction }) {
  const [, neut, opt] = c.riskmodel;
  const fifo = c.tax.find((t) => t.method === 'fifo');
  const hifo = c.tax.find((t) => t.method === 'hifo');
  const taxSaved = fifo && hifo && fifo.tax != null && hifo.tax != null ? fifo.tax - hifo.tax : null;

  const layers = [
    {
      name: 'Multi-factor composite', sub: 'value · quality · momentum',
      what: <>Blends the weak factors into one cross-sectional score, so uncorrelated signals reinforce and their noise cancels.</>,
      result: `IC t ${sh(c.composite.ic_t)}`, resultSub: 'a significant combined forecast (t>2 is the bar)',
    },
    {
      name: 'Risk-model optimizer', sub: 'Barra Σ = BFBᵀ+D · constrained MVO',
      what: <>Risk-weights the same alpha and caps position size &amp; turnover — the <b>investable</b> form of the book.</>,
      result: `${sh(opt?.net_sharpe)} Sharpe`, resultSub: `from ${sh(neut?.net_sharpe)} · DD ${pct(opt?.max_drawdown)} · turnover ${num(opt?.turnover)}`,
    },
    {
      name: 'Regime timing', sub: 'FRED credit spreads + VIX',
      what: <>Cuts equity exposure when credit and volatility flash risk-off — drawdown control, not new alpha.</>,
      result: `${pct(c.timing.dd_cut)} cut`, resultSub: `max drawdown ${pct(c.timing.mkt_raw_dd)} → ${pct(c.timing.mkt_timed_dd)}`,
    },
    c.structuring.available ? {
      name: 'Options structuring', sub: 'live IV surface',
      what: <>Sizes tail hedges and harvests the variance-risk premium off the live options surface.</>,
      result: `${c.structuring.vrp_count}/${c.structuring.n_names} rich`, resultSub: `tail hedge ~${pct(c.structuring.tail_hedge?.annual_drag)}/yr`,
    } : null,
    taxSaved != null ? {
      name: 'Tax-aware rebalancing', sub: 'HIFO · wash sales · §475(f)',
      what: <>HIFO lot selection defers gains and shifts them to the lower long-term rate — pure after-tax edge.</>,
      result: `${money(taxSaved)} saved`, resultSub: 'HIFO vs FIFO on identical trades ($1M book)',
    } : null,
  ].filter(Boolean) as { name: string; sub: string; what: ReactNode; result: string; resultSub: string }[];

  return (
    <Chapter
      num="02 — The Edge Is Construction"
      title="So don't hunt a signal — build a portfolio"
      lede={<>If no single factor works, the quant move isn't a cleverer signal — it's how you <b>construct and
        manage</b> the portfolio. Five layers, each measured against a naive baseline. The composite's forecast
        is statistically significant (IC t {sh(c.composite.ic_t)}) yet still under the best single factor
        ({c.composite.best_single_label} {sh(c.composite.best_single_sharpe)}): combining cuts noise, it can't
        conjure absent alpha. The value shows up in the <b>construction</b>:</>}
    >
      <div className="layers">
        {layers.map((l) => (
          <div key={l.name} className="layer-card">
            <div className="lc-name">{l.name}<small>{l.sub}</small></div>
            <div className="lc-what">{l.what}</div>
            <div className="lc-result">{l.result}<small>{l.resultSub}</small></div>
          </div>
        ))}
      </div>

      <Callout figure="⅓ the drawdown">
        The optimizer delivers the <b>same</b> alpha at a third of the drawdown ({pct(neut?.max_drawdown)} →{' '}
        {pct(opt?.max_drawdown)}) and a tenth of the turnover — and none of these layers needs a significant
        standalone signal. <b>When alpha is scarce, construction and risk control are the edge.</b>
      </Callout>
    </Chapter>
  );
}

// ── Chapter 3: microstructure — the daily cross-section is null, but zoom in to order flow and the
// signal is genuinely there. The whole question becomes whether it survives execution cost. This is
// the interactive heart of the story and the bridge to the sibling Exchange product (same OFI). ──

const SIG_BLURB: Record<string, string> = {
  ofi: 'Net signed order flow — the single best short-horizon predictor (Cont–Kukanov–Stoikov).',
  ofi_smooth: 'A 5-tick average of OFI: less noise, but the averaging adds lag and dilutes the edge.',
  queue_imb: 'Top-of-book size imbalance — a weaker, noisier shadow of true order flow.',
};

/** Linear-interpolate net Sharpe at an arbitrary cost from the discrete sweep. */
function interpNet(sweep: MicroSweepPoint[], cost: number): number {
  if (!sweep.length) return 0;
  if (cost <= sweep[0].cost_bps) return sweep[0].net_sharpe;
  for (let i = 1; i < sweep.length; i++) {
    if (cost <= sweep[i].cost_bps) {
      const a = sweep[i - 1], b = sweep[i];
      const w = (cost - a.cost_bps) / (b.cost_bps - a.cost_bps || 1);
      return a.net_sharpe + w * (b.net_sharpe - a.net_sharpe);
    }
  }
  return sweep[sweep.length - 1].net_sharpe;
}

function MicrostructureChapter() {
  const [study, setStudy] = useState<MicroStudy | null>(null);
  const [signal, setSignal] = useState('ofi');
  const [ic, setIc] = useState(0.1);
  const [cost, setCost] = useState(0.5); // the cost cursor, in bps round-trip
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      api.researchMicrostructure(ic, signal)
        .then((s) => { if (alive) { setStudy(s); setDown(false); } })
        .catch(() => { if (alive) setDown(true); });
    }, 160);
    return () => { alive = false; clearTimeout(t); };
  }, [ic, signal]);

  const menu = study?.menu ?? [];
  const netAtCursor = useMemo(() => interpNet(study?.cost_sweep ?? [], cost), [study, cost]);
  const be = study?.breakeven_cost_bps ?? null;
  const tradable = be != null && cost < be;

  return (
    <Chapter
      num="03 — Where The Signal Actually Is"
      title="Order flow predicts the next move — cost decides if it's an edge"
      lede={<>The daily cross-section came back null. So <b>go faster.</b> At the microstructure horizon,
        order-flow imbalance genuinely forecasts the next tick — but you pay the spread on every decision.
        This runs an <b>event-driven backtest</b> on an order-flow tape with a <i>known</i> ground-truth IC,
        so you can watch a real signal turn tradable or not as the only thing that changes is execution cost.
        It's the same order-flow imbalance the <b>Exchange</b> book shows — here measured as alpha.</>}
    >
      {down && (
        <div className="banner err" style={{ marginBottom: 16 }}>
          Microstructure endpoint unreachable at <code>/research-api/microstructure</code>.
        </div>
      )}

      <div className="micro-controls">
        <label className="lab2-field">
          <span>Signal</span>
          <select value={signal} onChange={(e) => setSignal(e.target.value)}>
            {(menu.length ? menu : [{ name: 'ofi', label: 'Order-Flow Imbalance' }]).map((s) => (
              <option key={s.name} value={s.name}>{s.label}</option>
            ))}
          </select>
        </label>
        <label className="lab2-field">
          <span>Signal strength — true 1-step IC: {ic.toFixed(2)}</span>
          <input type="range" min={0} max={0.3} step={0.01} value={ic} onChange={(e) => setIc(Number(e.target.value))} />
        </label>
        <label className="lab2-field">
          <span>Execution cost — round-trip: {cost.toFixed(2)} bps</span>
          <input type="range" min={0} max={1} step={0.01} value={cost} onChange={(e) => setCost(Number(e.target.value))} />
        </label>
      </div>
      <p className="mctx-ctx" style={{ marginTop: -4 }}>{SIG_BLURB[signal] ?? ''}</p>

      <div className="micro-grid">
        <div className="micro-chart">
          <div className="micro-chart-head">
            <h4>Signal decay — information coefficient by horizon</h4>
            <span>strongest one step out, fades like IC/√h (dashed)</span>
          </div>
          <IcDecayChart points={study?.ic_decay ?? []} />
          <p className="micro-cap">Rank correlation of the signal with the forward return over h ticks.
            A microstructure edge lives in the first few ticks — act late and it's gone.</p>
        </div>

        <div className="micro-chart">
          <div className="micro-chart-head">
            <h4>Does it survive costs? — Sharpe vs round-trip cost</h4>
            <span>gross is predictive; the gap to net is the cost drag</span>
          </div>
          <CostSweepChart sweep={study?.cost_sweep ?? []} breakeven={be} cursor={cost} gross={study?.gross_sharpe ?? 0} />
          <p className="micro-cap">At tick frequency you flip position almost every step, so turnover — and
            cost — is enormous. The break-even is where a genuinely predictive signal stops paying.</p>
        </div>
      </div>

      <div className="micro-readout">
        <MetricCtx label="Gross Sharpe" value={sh(study?.gross_sharpe)} tone="good"
          ctx="costless — the signal is genuinely predictive" />
        <MetricCtx label="Break-even cost" value={be == null ? '> grid' : `${be.toFixed(2)} bps`} tone="warn"
          ctx="round-trip cost above which net Sharpe ≤ 0" />
        <MetricCtx label={`Net Sharpe @ ${cost.toFixed(2)}bps`} value={sh(netAtCursor)}
          tone={netAtCursor >= 0 ? 'good' : 'bad'} ctx={tradable ? 'below break-even — an edge' : 'above break-even — dies to cost'} />
        <MetricCtx label="Net @ 0.5bps (HAC t)" value={sh(study?.representative.hac_t)}
          ctx="significance of the net edge at a realistic taker cost" />
      </div>

      <Callout figure={be == null ? '—' : `${be.toFixed(2)} bps`} tone="warn">
        {study?.verdict ?? 'Running the order-flow study…'}
      </Callout>
    </Chapter>
  );
}

/** IC-by-horizon decay, plotted on a log-horizon axis with the theoretical IC/√h reference dashed. */
function IcDecayChart({ points }: { points: MicroDecayPoint[] }) {
  if (points.length < 2) return <div className="empty" style={{ padding: 40 }}>loading…</div>;
  const W = 600, H = 220, m = { l: 42, r: 14, t: 14, b: 32 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const maxLogH = Math.log(Math.max(...points.map((p) => p.horizon)));
  const ymax = Math.max(...points.map((p) => p.ic), 0.02) * 1.15;
  const x = (h: number) => m.l + (Math.log(h) / (maxLogH || 1)) * pw;
  const y = (v: number) => m.t + (1 - v / ymax) * ph;
  const ic1 = points[0].ic;
  const line = points.map((p) => `${x(p.horizon).toFixed(1)},${y(p.ic).toFixed(1)}`).join(' ');
  const ref = points.map((p) => `${x(p.horizon).toFixed(1)},${y(ic1 / Math.sqrt(p.horizon)).toFixed(1)}`).join(' ');
  const yTicks = [0, ymax / 2, ymax];
  return (
    <svg className="eqchart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="information coefficient by horizon">
      {yTicks.map((v, k) => (
        <g key={k}>
          <line className="eqc-grid" x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} />
          <text className="eqc-tick" x={m.l - 6} y={y(v) + 3} textAnchor="end">{v.toFixed(2)}</text>
        </g>
      ))}
      <polyline points={ref} fill="none" stroke="var(--muted)" strokeWidth={1.3} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
      <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      {points.map((p, i) => <circle key={i} cx={x(p.horizon)} cy={y(p.ic)} r={2.6} fill="var(--accent)" />)}
      {points.map((p, i) => (
        <text key={`t${i}`} className="eqc-tick" x={x(p.horizon)} y={H - 8}
          textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{p.horizon}</text>
      ))}
      <text className="eqc-tick" x={(m.l + W - m.r) / 2} y={H - 8 - 12} textAnchor="middle" style={{ fill: 'var(--muted)', opacity: 0 }}>h</text>
    </svg>
  );
}

/** Gross vs net Sharpe as round-trip cost rises, with the break-even and a movable cost cursor. */
function CostSweepChart({ sweep, breakeven, cursor, gross }: {
  sweep: MicroSweepPoint[]; breakeven: number | null; cursor: number; gross: number;
}) {
  if (sweep.length < 2) return <div className="empty" style={{ padding: 40 }}>loading…</div>;
  const W = 600, H = 220, m = { l: 42, r: 14, t: 14, b: 32 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const maxCost = Math.max(...sweep.map((s) => s.cost_bps));
  const yTop = Math.max(gross, 4) * 1.1;
  const yBot = -Math.max(gross, 4) * 1.1;              // symmetric window around zero; deep-negative tail clips
  const x = (c: number) => m.l + (c / (maxCost || 1)) * pw;
  const y = (v: number) => m.t + (1 - (v - yBot) / (yTop - yBot)) * ph;
  const clip = (v: number) => Math.max(yBot, Math.min(yTop, v));
  const netLine = sweep.map((s) => `${x(s.cost_bps).toFixed(1)},${y(clip(s.net_sharpe)).toFixed(1)}`).join(' ');
  const grossLine = `${x(0).toFixed(1)},${y(clip(gross)).toFixed(1)} ${x(maxCost).toFixed(1)},${y(clip(gross)).toFixed(1)}`;
  const cursorNet = clip(interpNet(sweep, cursor));
  const y0 = y(0);
  return (
    <svg className="eqchart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="gross and net Sharpe versus cost">
      {/* untradable zone: cost beyond break-even */}
      {breakeven != null && breakeven < maxCost && (
        <rect x={x(breakeven)} y={m.t} width={x(maxCost) - x(breakeven)} height={ph} fill="var(--sell)" fillOpacity={0.05} />
      )}
      {/* zero baseline */}
      <line x1={m.l} x2={W - m.r} y1={y0} y2={y0} stroke="var(--muted)" strokeWidth={1} />
      <text className="eqc-tick" x={m.l - 6} y={y0 + 3} textAnchor="end">0</text>
      <text className="eqc-tick" x={m.l - 6} y={y(clip(gross)) + 3} textAnchor="end">{gross.toFixed(0)}</text>
      {/* gross (flat, costless) */}
      <polyline points={grossLine} fill="none" stroke="var(--buy)" strokeWidth={1.6} strokeDasharray="5 3" vectorEffect="non-scaling-stroke" />
      <text className="eqc-tick" x={x(0) + 4} y={y(clip(gross)) - 5} style={{ fill: 'var(--buy)' }}>gross (costless)</text>
      {/* net */}
      <polyline points={netLine} fill="none" stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      {/* break-even marker */}
      {breakeven != null && breakeven <= maxCost && (
        <g>
          <line x1={x(breakeven)} x2={x(breakeven)} y1={m.t} y2={m.t + ph} stroke="var(--warn)" strokeWidth={1.2} strokeDasharray="3 3" />
          <text className="eqc-tick" x={x(breakeven)} y={m.t + 10} textAnchor="middle" style={{ fill: 'var(--warn)' }}>
            break-even {breakeven.toFixed(2)}
          </text>
        </g>
      )}
      {/* cost cursor */}
      <line x1={x(cursor)} x2={x(cursor)} y1={m.t} y2={m.t + ph} stroke="var(--ink)" strokeWidth={1} strokeOpacity={0.5} />
      <circle cx={x(cursor)} cy={y(cursorNet)} r={3.5} fill={cursorNet >= 0 ? 'var(--buy)' : 'var(--sell)'} />
      {/* x ticks */}
      {[0, maxCost / 2, maxCost].map((c, k) => (
        <text key={k} className="eqc-tick" x={x(c)} y={H - 8} textAnchor={k === 0 ? 'start' : k === 2 ? 'end' : 'middle'}>{c.toFixed(2)} bps</text>
      ))}
    </svg>
  );
}
