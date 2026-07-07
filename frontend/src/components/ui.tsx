import type { ReactNode } from 'react';
import type { EquityPoint } from '../api/types';

// Shared design-system primitives — the reference vocabulary for hierarchy + explanation that every
// surface will use: numbered narrative chapters, punchline callouts, contextual metrics (value +
// what it means + what "good" is), and a properly-labeled chart.

export function Chapter({ num, title, lede, children }: {
  num: string; title: string; lede: ReactNode; children: ReactNode;
}) {
  return (
    <section className="chapter">
      <div className="chapter-head">
        <span className="chapter-num">{num}</span>
        <h2 className="chapter-title">{title}</h2>
        <p className="chapter-lede">{lede}</p>
      </div>
      {children}
    </section>
  );
}

export function Callout({ figure, tone, children }: { figure: string; tone?: 'accent' | 'warn'; children: ReactNode }) {
  return (
    <div className={`callout ${tone === 'warn' ? 'warn' : ''}`}>
      <span className="callout-figure">{figure}</span>
      <span className="callout-body">{children}</span>
    </div>
  );
}

/** A metric that explains itself: the number, what it is, and what a good value looks like. */
export function MetricCtx({ label, value, ctx, tone }: {
  label: string; value: string; ctx: string; tone?: 'good' | 'bad' | 'warn';
}) {
  return (
    <div className="mctx">
      <span className="mctx-label">{label}</span>
      <span className={`mctx-value ${tone ?? ''}`}>{value}</span>
      <span className="mctx-ctx">{ctx}</span>
    </div>
  );
}

/**
 * Growth-of-$1 equity curve with real axes: a value scale on the left (with gridlines), a date scale
 * along the bottom, and a labeled 1.0 baseline so the reader can actually read the chart.
 */
export function EquityChart({ curve, up }: { curve: EquityPoint[]; up: boolean }) {
  if (!curve || curve.length < 2) {
    return <div className="empty" style={{ padding: '48px' }}>run a backtest to see the curve…</div>;
  }
  const W = 640, H = 280;
  const m = { l: 46, r: 16, t: 16, b: 30 };
  const plotW = W - m.l - m.r;
  const plotH = H - m.t - m.b;

  const vals = curve.map((p) => p.value);
  const dataMin = Math.min(...vals, 1);
  const dataMax = Math.max(...vals, 1);
  const pad = (dataMax - dataMin || 0.1) * 0.1;
  const lo = dataMin - pad, hi = dataMax + pad;

  const x = (i: number) => m.l + (i / (curve.length - 1)) * plotW;
  const y = (v: number) => m.t + (1 - (v - lo) / (hi - lo)) * plotH;

  const yTicks = Array.from({ length: 4 }, (_, k) => lo + (k / 3) * (hi - lo));
  const xIdx = [0, Math.floor((curve.length - 1) / 3), Math.floor((2 * (curve.length - 1)) / 3), curve.length - 1];
  const line = curve.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const area = `${x(0).toFixed(1)},${(m.t + plotH).toFixed(1)} ${line} ${x(curve.length - 1).toFixed(1)},${(m.t + plotH).toFixed(1)}`;
  const color = up ? 'var(--buy)' : 'var(--sell)';
  const last = curve[curve.length - 1];

  return (
    <svg className="eqchart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="cumulative return equity curve">
      {/* y gridlines + value labels */}
      {yTicks.map((v, k) => (
        <g key={k}>
          <line className="eqc-grid" x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} />
          <text className="eqc-tick" x={m.l - 6} y={y(v) + 3} textAnchor="end">{v.toFixed(2)}×</text>
        </g>
      ))}
      {/* 1.0 baseline (starting capital) */}
      <line className="eqc-base" x1={m.l} x2={W - m.r} y1={y(1)} y2={y(1)} />
      <text className="eqc-tick" x={W - m.r} y={y(1) - 4} textAnchor="end" style={{ fill: 'var(--muted)' }}>start · $1</text>
      {/* x date labels */}
      {xIdx.map((i, k) => (
        <text key={k} className="eqc-tick" x={x(i)} y={H - 8} textAnchor={k === 0 ? 'start' : k === xIdx.length - 1 ? 'end' : 'middle'}>
          {curve[i].date.slice(0, 7)}
        </text>
      ))}
      {/* series */}
      <polygon points={area} fill={color} fillOpacity={0.1} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <circle cx={x(curve.length - 1)} cy={y(last.value)} r={3} fill={color} />
    </svg>
  );
}
