import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { LabCurvePoint, LabResult, LabTemplate, LabTemplates, LabUniverse } from '../api/types';

// Backtest — vet a signal over real Alpaca history before it trades paper money. The backtest runs the
// SAME signal code the live engine uses, so what you test is what trades. A survivor promotes straight
// to a live (disarmed) strategy. Controls edit parameters; the code shown is the exact logic that runs.

const pct = (n: number | null | undefined, dp = 1) => (n == null ? '—' : (n >= 0 ? '+' : '') + (n * 100).toFixed(dp) + '%');
const sh = (n: number | null | undefined) => (n == null ? '—' : (n >= 0 ? '+' : '') + n.toFixed(2));
const num = (n: number | null | undefined, dp = 2) => (n == null ? '—' : n.toFixed(dp));

export function BacktestTab() {
  const [meta, setMeta] = useState<LabTemplates | null>(null);
  const [kind, setKind] = useState('ma_crossover');
  const [symbol, setSymbol] = useState('BTC/USD');
  const [timeframe, setTimeframe] = useState('1Hour');
  const [costBps, setCostBps] = useState(25);
  const [params, setParams] = useState<Record<string, number>>({ fast: 12, slow: 48, lookback: 24 });
  const [result, setResult] = useState<LabResult | null>(null);
  const [running, setRunning] = useState(false);
  const [promoted, setPromoted] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.labTemplates().then(setMeta).catch(() => setErr('lab unavailable')); }, []);

  const tpl: LabTemplate | undefined = meta?.templates.find((t) => t.kind === kind);
  const uni: LabUniverse | undefined = meta?.universe.find((u) => u.symbol === symbol);

  const run = useCallback(async () => {
    setRunning(true); setErr(null); setPromoted(null);
    try {
      const r = await api.labBacktest({ kind, symbol, timeframe, cost_bps: costBps, fast: params.fast, slow: params.slow, lookback: params.lookback });
      setResult(r);
      if (!r.ok) setErr(r.reason ?? 'backtest failed');
    } catch {
      setErr('backtest request failed');
    } finally {
      setRunning(false);
    }
  }, [kind, symbol, timeframe, costBps, params]);

  useEffect(() => { if (meta) void run(); /* run once meta loads */ /* eslint-disable-next-line */ }, [meta]);

  const promote = useCallback(async () => {
    if (!tpl) return;
    const p: Record<string, number> = tpl.kind === 'ma_crossover'
      ? { fast: params.fast, slow: params.slow }
      : { lookback: params.lookback };
    try {
      const r = await api.labPromote({ kind, symbol, timeframe, params: p, notional: 1500 });
      setPromoted(r.name);
    } catch {
      setErr('promote failed');
    }
  }, [tpl, kind, symbol, timeframe, params]);

  const codeText = useMemo(() => {
    if (!tpl) return '';
    return tpl.code.replace(/\{(\w+)\}/g, (_, k: string) => String(params[k] ?? `{${k}}`));
  }, [tpl, params]);

  if (!meta) {
    return <main className="live-main"><div className="live-loading">{err ?? 'loading lab…'}</div></main>;
  }

  const activeParams = tpl?.params ?? [];

  return (
    <main className="live-main">
      <div className="live-intro"><span className="dot" /> Backtest — vet a signal over real history, then promote the survivor to live</div>

      <div className="bt-grid">
        {/* ---- controls ---- */}
        <section className="live-card bt-controls">
          <div className="bt-field">
            <span>Strategy template</span>
            <div className="bt-seg">
              {meta.templates.map((t) => (
                <button key={t.kind} className={t.kind === kind ? 'on' : ''} onClick={() => { setKind(t.kind); }}>{t.name}</button>
              ))}
            </div>
          </div>
          <p className="bt-tpl-desc">{tpl?.desc}</p>

          <div className="bt-row">
            <label className="bt-field">
              <span>Symbol</span>
              <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {meta.universe.map((u) => <option key={u.symbol} value={u.symbol}>{u.label} · {u.symbol}</option>)}
              </select>
            </label>
            <label className="bt-field">
              <span>Timeframe</span>
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {meta.timeframes.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>

          {activeParams.map((p) => (
            <label key={p.key} className="bt-field">
              <span>{p.label}: {params[p.key]}</span>
              <input type="range" min={p.min} max={p.max} step={1} value={params[p.key]}
                onChange={(e) => setParams((s) => ({ ...s, [p.key]: Number(e.target.value) }))} />
            </label>
          ))}

          <label className="bt-field">
            <span>Execution cost: {costBps} bps per side {costBps < 25 ? '(below live taker fee)' : ''}</span>
            <input type="range" min={0} max={50} step={1} value={costBps} onChange={(e) => setCostBps(Number(e.target.value))} />
          </label>

          <button className="btn primary bt-run" onClick={run} disabled={running}>{running ? 'Running…' : 'Run backtest'}</button>

          <div className="bt-code">
            <div className="bt-code-head">signal · the exact code that runs live</div>
            <pre>{codeText}</pre>
          </div>
        </section>

        {/* ---- results ---- */}
        <section className="live-card bt-result">
          {err && !result?.ok ? (
            <div className="bt-err">{err}</div>
          ) : result && result.ok ? (
            <>
              <div className="bt-result-head">
                <div>
                  <h3>{result.symbol} · {result.timeframe}</h3>
                  <span>{result.n_bars} {result.freq} bars (~{result.window_days}d) · net of {result.cost_bps} bps/side · in-sample, causal</span>
                </div>
                <span className={`bt-verdict-chip ${result.passes ? 'pass' : result.net_sharpe > 0 ? 'weak' : 'fail'}`}>
                  {result.passes ? 'CANDIDATE'
                    : result.significant && !result.realistic_cost ? 'RAISE COST'
                    : result.underpowered && result.net_sharpe > 0 ? 'UNDERPOWERED'
                    : result.net_sharpe > 0 ? 'NOT SIGNIFICANT' : 'COSTED LOSER'}
                </span>
              </div>

              <BtEquity curve={result.equity_curve} up={result.total_return >= 0} />

              <div className="bt-stats">
                <Stat label="Net Sharpe" value={sh(result.net_sharpe)} tone={result.net_sharpe >= 0 ? 'good' : 'bad'} ctx={`${result.freq}, annualized (×√${result.bars_per_year})`} />
                <Stat label="HAC t-stat" value={sh(result.hac_t)} ctx={`bar |t|>${result.bar_t.toFixed(1)} (search-corrected, ~${result.trials} tries)`} />
                <Stat label="Bootstrap Sharpe CI" value={result.boot_lo == null ? '—' : `${sh(result.boot_lo)}…${sh(result.boot_hi)}`}
                  ctx="95% · block bootstrap · spans 0 = not significant" />
                <Stat label="Min detectable" value={sh(result.min_detectable)} tone={result.underpowered ? 'bad' : undefined}
                  ctx={`smallest Sharpe this ${result.n_bars}-bar sample can see`} />
                <Stat label="Total return" value={pct(result.total_return)} tone={result.total_return >= 0 ? 'good' : 'bad'} ctx="over the window (not annualized)" />
                <Stat label="Max drawdown" value={pct(result.max_drawdown)} tone="bad" ctx="worst peak-to-trough" />
                <Stat label="Turnover" value={num(result.avg_turnover, 3)} ctx="per bar · lower = cheaper" />
                <Stat label="Hit rate" value={pct(result.hit_rate, 0)} ctx="of in-position bars" />
              </div>

              <div className={`bt-verdict ${result.passes ? 'good' : 'warn'}`}>{result.verdict}</div>

              <div className="bt-promote">
                {promoted ? (
                  <div className="bt-promoted">✓ Promoted <b>{promoted}</b> — it's on the Live desk (disarmed). Arm it there to trade.</div>
                ) : uni?.promotable ? (
                  <button className="btn primary" onClick={promote} disabled={!result.passes}
                    title={result.passes ? '' : 'must clear the search-corrected bar to promote'}>
                    Promote to live strategy →
                  </button>
                ) : (
                  <span className="bt-noprom">{result.symbol} is evaluate-only — live trading is crypto (24/7) for now.</span>
                )}
                {uni?.promotable && !result.passes && <span className="bt-promote-note">Only a candidate — clearing the <b>search-corrected</b> bar (|t|&gt;{result.bar_t.toFixed(1)}) with a bootstrap CI above zero — can be promoted. That's the multiple-testing defense.</span>}
              </div>
            </>
          ) : (
            <div className="live-loading">{running ? 'running backtest…' : 'run a backtest to see results'}</div>
          )}
        </section>
      </div>
    </main>
  );
}

function Stat({ label, value, ctx, tone }: { label: string; value: string; ctx: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="bt-stat">
      <span className="bt-stat-l">{label}</span>
      <b className={`bt-stat-v ${tone ?? ''}`}>{value}</b>
      <span className="bt-stat-c">{ctx}</span>
    </div>
  );
}

function BtEquity({ curve, up }: { curve: LabCurvePoint[]; up: boolean }) {
  if (curve.length < 2) return <div className="live-empty">no curve</div>;
  const W = 620, H = 200, m = { l: 46, r: 14, t: 12, b: 22 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const vals = curve.map((p) => p.value);
  const lo = Math.min(...vals, 1), hi = Math.max(...vals, 1);
  const pad = (hi - lo || 0.1) * 0.1;
  const yLo = lo - pad, yHi = hi + pad;
  const x = (i: number) => m.l + (i / (curve.length - 1)) * pw;
  const y = (v: number) => m.t + (1 - (v - yLo) / (yHi - yLo)) * ph;
  const color = up ? 'var(--buy)' : 'var(--sell)';
  const line = curve.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const area = `${x(0).toFixed(1)},${(m.t + ph).toFixed(1)} ${line} ${x(curve.length - 1).toFixed(1)},${(m.t + ph).toFixed(1)}`;
  const yTicks = [yLo, (yLo + yHi) / 2, yHi];
  return (
    <svg className="eqchart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="backtest equity curve">
      {yTicks.map((v, k) => (
        <g key={k}>
          <line className="eqc-grid" x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} />
          <text className="eqc-tick" x={m.l - 6} y={y(v) + 3} textAnchor="end">{v.toFixed(2)}×</text>
        </g>
      ))}
      <line className="eqc-base" x1={m.l} x2={W - m.r} y1={y(1)} y2={y(1)} />
      <polygon points={area} fill={color} fillOpacity={0.1} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
