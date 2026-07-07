import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { BacktestResult, Construction, EquityPoint, Findings, SignalMeta } from '../api/types';

// The Research Lab — the strongest work, made legible. Two halves:
//   1. an INTERACTIVE runner: pick a signal / cost / neutralization → live backtest with honest,
//      overfitting-adjusted stats (HAC t, bootstrap CI, Bonferroni bar);
//   2. the TOLD STORY from a precomputed snapshot: the honest single-factor null, then why the
//      construction stack (composite → risk model → timing → structuring → tax) is the real edge.

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

  // Initial run so the panel isn't empty on arrival (composite @ 5bps, neutralized).
  useEffect(() => { void run(); /* eslint-disable-next-line */ }, []);

  if (down && !findings && !result) {
    return (
      <main className="risk-main">
        <div className="banner err global">
          Research service unreachable at <code>/research</code>. Start it from the{' '}
          <code>research/</code> directory:{' '}
          <code>pip install -r service/requirements.txt &amp;&amp; uvicorn service.app:app --port 8082</code>
        </div>
      </main>
    );
  }

  const u = findings?.universe;

  return (
    <main className="risk-main">
      <div className="risk-intro">
        <span className="dot live" />
        The <b>quant research</b> layer, live — factor backtests over the Python <code>mds</code> engine,
        reported with <b>honest, overfitting-adjusted statistics</b> (Newey–West t, Deflated Sharpe, PBO).
      </div>

      {/* ---- interactive runner ---- */}
      <div className="panel lab-runner">
        <div className="panel-head">
          <h2>Interactive Backtest</h2>
          <span className="count">dollar-neutral, walk-forward, net of cost</span>
        </div>
        <div className="lab-body">
          <div className="lab-controls">
            <label className="lab-field">
              <span>Signal</span>
              <select value={signal} onChange={(e) => setSignal(e.target.value)}>
                {signals.map((s) => (
                  <option key={s.name} value={s.name}>{s.label}</option>
                ))}
              </select>
            </label>
            <label className="lab-field">
              <span>Cost (bps): {costBps}</span>
              <input type="range" min={0} max={30} step={1} value={costBps}
                onChange={(e) => setCostBps(Number(e.target.value))} />
            </label>
            <label className="lab-field toggle">
              <span>β + sector neutral</span>
              <input type="checkbox" checked={neutralize} onChange={(e) => setNeutralize(e.target.checked)} />
            </label>
            <button className="lab-run" onClick={run} disabled={running}>
              {running ? 'Running…' : 'Run backtest'}
            </button>
          </div>

          {result && (
            <div className="lab-result">
              <EquityCurve curve={result.equity_curve} up={(result.net_sharpe ?? 0) >= 0} />
              <div className="lab-stats">
                <Stat label="Net Sharpe" value={sh(result.net_sharpe)} tone={(result.net_sharpe ?? 0) >= 0 ? 'good' : 'bad'} />
                <Stat label="HAC t-stat" value={sh(result.hac_t)} />
                <Stat label="Bootstrap 95% CI" value={`${sh(result.boot_lo)} … ${sh(result.boot_hi)}`} />
                <Stat label="Ann. return" value={pct(result.ann_return)} tone={(result.ann_return ?? 0) >= 0 ? 'good' : 'bad'} />
                <Stat label="Max drawdown" value={pct(result.max_drawdown)} tone="bad" />
                <Stat label="Turnover" value={num(result.avg_turnover)} />
              </div>
              <div className={`lab-verdict ${result.significant ? (result.net_sharpe && result.net_sharpe > 0 ? 'good' : 'warn') : 'neutral'}`}>
                <span className="lv-chip">
                  {result.significant ? (result.net_sharpe && result.net_sharpe > 0 ? 'CANDIDATE' : 'SIGNIFICANT LOSER') : 'NOT SIGNIFICANT'}
                </span>
                {result.verdict}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ---- told story 1: the honest null ---- */}
      {findings && (
        <div className="panel">
          <div className="panel-head">
            <h2>The Honest Null — single factors</h2>
            {u && <span className="count">{u.names} names · {u.days} days · {u.start} → {u.end}</span>}
          </div>
          <div className="lab-findings">
            <div className="tablewrap">
              <table className="data-table">
                <thead>
                  <tr><th>Factor</th><th>Family</th><th className="r">Net Sharpe</th><th className="r">HAC t</th><th className="r">Turnover</th><th className="r">Sig?</th></tr>
                </thead>
                <tbody>
                  {findings.signals.slice(0, 10).map((r) => (
                    <tr key={r.name}>
                      <td>{r.label}</td>
                      <td className="dim">{r.family}</td>
                      <td className={`r mono ${(r.net_sharpe ?? 0) >= 0 ? 'pos' : 'neg'}`}>{sh(r.net_sharpe)}</td>
                      <td className="r mono">{sh(r.hac_t)}</td>
                      <td className="r mono dim">{num(r.turnover)}</td>
                      <td className="r">{r.significant ? <span className="tag-sig">yes</span> : <span className="tag-no">no</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="lab-selection">
              <SelStat label="Best factor" value={findings.selection.best_label} />
              <SelStat label="Deflated Sharpe" value={num(findings.selection.deflated_sharpe)} hint="needs > 0.95" />
              <SelStat label="PBO" value={num(findings.selection.pbo)} hint="prob. overfit" />
              <SelStat label="Bonferroni bar" value={`|t| > ${num(findings.selection.bonferroni_z)}`} hint={`${findings.selection.n_trials} trials`} />
            </div>
          </div>
          <p className="lab-note">{findings.verdict}</p>
        </div>
      )}

      {/* ---- told story 2: why construction is the edge ---- */}
      {construction && <ConstructionStory c={construction} />}
    </main>
  );
}

function ConstructionStory({ c }: { c: Construction }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Why Construction Is the Edge</h2>
        <span className="count">combine → risk-model → time → hedge → tax</span>
      </div>
      <div className="constr-grid">
        <div className="constr-cell">
          <h3>1 · Multi-factor composite</h3>
          <p>IC t <b>{sh(c.composite.ic_t)}</b> (positive &amp; significant), but neutral Sharpe{' '}
            <b>{sh(c.composite.net_sharpe)}</b> still &lt; best single ({c.composite.best_single_label}{' '}
            {sh(c.composite.best_single_sharpe)}). Combining lowers noise; it can't create absent alpha.</p>
        </div>

        <div className="constr-cell">
          <h3>2 · Risk-model optimizer</h3>
          <div className="tablewrap">
            <table className="data-table sm">
              <thead><tr><th>Book</th><th className="r">Sharpe</th><th className="r">Turn</th><th className="r">|β|</th><th className="r">Max DD</th></tr></thead>
              <tbody>
                {c.riskmodel.map((b) => (
                  <tr key={b.book}>
                    <td>{b.book}</td>
                    <td className="r mono">{sh(b.net_sharpe)}</td>
                    <td className="r mono dim">{num(b.turnover)}</td>
                    <td className="r mono dim">{num(b.net_beta, 3)}</td>
                    <td className="r mono neg">{pct(b.max_drawdown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="constr-cell">
          <h3>3 · Regime exposure timing</h3>
          <p>Directional book, timed on the FRED credit/VIX state:</p>
          <div className="mini-metrics">
            <span>max DD <b className="neg">{pct(c.timing.mkt_raw_dd)}</b> → <b className="pos">{pct(c.timing.mkt_timed_dd)}</b></span>
            <span className="cut">drawdown cut {pct(c.timing.dd_cut)}</span>
          </div>
        </div>

        <div className="constr-cell">
          <h3>4 · Options structuring</h3>
          {c.structuring.available ? (
            <p>
              Live surface ({c.structuring.n_names} names, IV&gt;RV on {c.structuring.vrp_count}). Tail hedge{' '}
              <b>{pct(c.structuring.tail_hedge?.annual_drag)}</b>/yr (cheap-entry {pct(c.structuring.tail_hedge?.cheap_drag)}).
              {c.structuring.overwrite && c.structuring.overwrite.length > 0 && (
                <> Overwrite: {c.structuring.overwrite.slice(0, 3).map((o) => o.symbol).join(', ')}.</>
              )}
            </p>
          ) : <p className="dim">No options snapshot cached.</p>}
        </div>

        <div className="constr-cell wide">
          <h3>5 · Tax-aware rebalancing</h3>
          <div className="tablewrap">
            <table className="data-table sm">
              <thead><tr><th>Method</th><th className="r">Tax</th><th className="r">Net ST</th><th className="r">Net LT</th><th className="r">LT% gains</th><th className="r">Deferred</th></tr></thead>
              <tbody>
                {c.tax.map((t) => (
                  <tr key={t.method} className={t.method === 'hifo' ? 'row-hi' : ''}>
                    <td className="up">{t.method}</td>
                    <td className="r mono">{money(t.tax)}</td>
                    <td className="r mono dim">{money(t.net_short_term)}</td>
                    <td className="r mono dim">{money(t.net_long_term)}</td>
                    <td className="r mono dim">{pct(t.lt_fraction)}</td>
                    <td className="r mono">{money(t.deferred_gain)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <p className="lab-note">{c.verdict}</p>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="lab-stat">
      <span className="ls-label">{label}</span>
      <span className={`ls-value ${tone ?? ''}`}>{value}</span>
    </div>
  );
}

function SelStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="sel-stat">
      <span className="ss-label">{label}</span>
      <span className="ss-value">{value}</span>
      {hint && <span className="ss-hint">{hint}</span>}
    </div>
  );
}

/** Cumulative equity curve — area fill, a dashed 1.0 baseline, and an emphasized endpoint. */
function EquityCurve({ curve, up }: { curve: EquityPoint[]; up: boolean }) {
  if (!curve || curve.length < 2) return <div className="eq-empty">run a backtest…</div>;
  const vals = curve.map((p) => p.value);
  const min = Math.min(...vals, 1);
  const max = Math.max(...vals, 1);
  const range = max - min || 1;
  const w = 100;
  const h = 42;
  const x = (i: number) => (i / (curve.length - 1)) * w;
  const y = (v: number) => h - ((v - min) / range) * h;
  const line = curve.map((p, i) => `${x(i)},${y(p.value)}`).join(' ');
  const area = `0,${h} ${line} ${w},${h}`;
  const baseY = y(1);
  const color = up ? 'var(--buy)' : 'var(--sell)';
  const last = curve[curve.length - 1];
  return (
    <div className="eq-wrap">
      <svg className="eq-curve" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <polygon points={area} fill={color} fillOpacity={0.1} />
        <line x1={0} x2={w} y1={baseY} y2={baseY} className="eq-base" />
        <polyline points={line} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        <circle cx={x(curve.length - 1)} cy={y(last.value)} r={1.6} fill={color} />
      </svg>
      <div className="eq-axis">
        <span>{curve[0].date}</span>
        <span className="eq-final" style={{ color }}>×{last.value.toFixed(2)}</span>
        <span>{last.date}</span>
      </div>
    </div>
  );
}
