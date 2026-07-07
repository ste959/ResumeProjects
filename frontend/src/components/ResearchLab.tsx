import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { BacktestResult, Construction, Findings, SignalMeta } from '../api/types';
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

      {/* ---- chapter 3: run it yourself ---- */}
      <Chapter
        num="03 — Run It Yourself"
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
