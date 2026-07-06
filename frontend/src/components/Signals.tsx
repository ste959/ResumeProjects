import { useCallback, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { MicroSnapshot } from '../api/types';
import { usePolling } from '../hooks/usePolling';

const PRODUCTS = ['BTC-USD', 'ETH-USD', 'SOL-USD'];

/** Minimal SVG sparkline that stretches to its container. */
function Spark({ values, color, zero = false }: { values: number[]; color: string; zero?: boolean }) {
  if (values.length < 2) return <div className="empty">collecting…</div>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const h = 46;
  const w = 100;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / range) * h}`).join(' ');
  const zeroY = zero ? h - ((0 - min) / range) * h : null;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {zeroY != null && <line x1={0} x2={w} y1={zeroY} y2={zeroY} className="spark-zero" />}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function pearson(x: number[], y: number[]): number {
  const n = Math.min(x.length, y.length);
  if (n < 3) return NaN;
  let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
  for (let i = 0; i < n; i++) {
    sx += x[i]; sy += y[i]; sxx += x[i] * x[i]; syy += y[i] * y[i]; sxy += x[i] * y[i];
  }
  const cov = sxy - (sx * sy) / n;
  const vx = sxx - (sx * sx) / n;
  const vy = syy - (sy * sy) / n;
  return vx > 0 && vy > 0 ? cov / Math.sqrt(vx * vy) : NaN;
}

export function Signals() {
  const [product, setProduct] = useState('BTC-USD');
  const series = usePolling(useCallback(() => api.marketMicrostructure(product), [product]), 1500);
  const data: MicroSnapshot[] = series.data ?? [];

  const mids = data.map((d) => d.mid);
  const imb = data.map((d) => d.imbalance);
  const prem = data.map((d) => d.microPremiumBps);
  const spread = data.map((d) => d.spreadBps);
  const last = data[data.length - 1];

  // Information coefficient: does imbalance predict the forward mid move?
  const ic = useMemo(() => {
    const h = 5;
    if (data.length <= h + 3) return NaN;
    const x: number[] = [];
    const y: number[] = [];
    for (let i = 0; i + h < data.length; i++) {
      x.push(data[i].imbalance);
      y.push(Math.log(data[i + h].mid / data[i].mid));
    }
    return pearson(x, y);
  }, [data]);

  return (
    <div className="risk">
      <div className="market-head">
        <div className="product-tabs">
          {PRODUCTS.map((p) => (
            <button key={p} className={p === product ? 'active' : ''} onClick={() => setProduct(p)}>{p}</button>
          ))}
        </div>
        <div className="quote-strip">
          <span className="q">{data.length} samples · 1 Hz · ~3 min window</span>
        </div>
      </div>

      <div className="kpi-row">
        <div className="kpi">
          <div className="kpi-label">Book Imbalance</div>
          <div className="kpi-value" style={{ color: (last?.imbalance ?? 0) >= 0 ? '#059669' : '#dc2626' }}>
            {last ? last.imbalance.toFixed(3) : '—'}
          </div>
          <div className="kpi-sub">bid-heavy &gt; 0</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Microprice Premium</div>
          <div className="kpi-value">{last ? `${last.microPremiumBps.toFixed(2)} bps` : '—'}</div>
          <div className="kpi-sub">fair-value tilt vs mid</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Spread</div>
          <div className="kpi-value">{last ? `${last.spreadBps.toFixed(2)} bps` : '—'}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Imbalance IC (h=5)</div>
          <div className="kpi-value" style={{ color: Number.isNaN(ic) ? undefined : ic >= 0 ? '#059669' : '#dc2626' }}>
            {Number.isNaN(ic) ? '—' : ic.toFixed(3)}
          </div>
          <div className="kpi-sub">corr(imbalance, fwd return)</div>
        </div>
      </div>

      <div className="signal-grid">
        <SignalPanel title="Mid Price" value={last ? last.mid.toLocaleString() : '—'}>
          <Spark values={mids} color="#1d4ed8" />
        </SignalPanel>
        <SignalPanel title="Order-Book Imbalance" value={last ? last.imbalance.toFixed(3) : '—'}>
          <Spark values={imb} color="#7c3aed" zero />
        </SignalPanel>
        <SignalPanel title="Microprice Premium (bps)" value={last ? last.microPremiumBps.toFixed(2) : '—'}>
          <Spark values={prem} color="#059669" zero />
        </SignalPanel>
        <SignalPanel title="Spread (bps)" value={last ? last.spreadBps.toFixed(2) : '—'}>
          <Spark values={spread} color="#b45309" />
        </SignalPanel>
      </div>

      <div className="tca-note">
        Live microstructure computed from the Coinbase book each second. The information coefficient
        measures whether current order-book imbalance predicts the mid move 5 ticks ahead — a standard
        (and honestly weak, at this sampling) alpha check.
      </div>
    </div>
  );
}

function SignalPanel({ title, value, children }: { title: string; value: string; children: React.ReactNode }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        <span className="count mono">{value}</span>
      </div>
      <div className="spark-wrap">{children}</div>
    </div>
  );
}
