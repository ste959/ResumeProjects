import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { YieldCurve } from '../api/types';

// The benchmark yield curve the desk prices bonds off — the context for every RFQ (fair yield =
// interpolated curve yield at the bond's tenor + a credit spread).

export function YieldCurvePanel() {
  const [curve, setCurve] = useState<YieldCurve | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api.yieldCurve().then(setCurve).catch(() => setErr(true));
  }, []);

  return (
    <div className="panel curve-panel">
      <div className="panel-head">
        <h2>Benchmark Curve</h2>
        {curve && <span className="count">{curve.source} · {curve.asOf}</span>}
      </div>
      <div className="curve-body">
        {err && <div className="empty">curve unavailable</div>}
        {!err && !curve && <div className="empty">loading…</div>}
        {curve && <Curve tenors={curve.tenors} yields={curve.yields} />}
      </div>
    </div>
  );
}

function Curve({ tenors, yields }: { tenors: number[]; yields: number[] }) {
  if (tenors.length < 2) return <div className="empty">no curve points</div>;
  const w = 100;
  const h = 42;
  const pad = 3;
  const min = Math.min(...yields);
  const max = Math.max(...yields);
  const range = max - min || 1;
  const x = (i: number) => pad + (i / (tenors.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / range) * (h - 2 * pad);
  const line = tenors.map((_, i) => `${x(i)},${y(yields[i])}`).join(' ');
  const area = `${x(0)},${h} ${line} ${x(tenors.length - 1)},${h}`;
  const label = (t: number) => (t < 1 ? `${t * 12}m` : `${t}y`);

  return (
    <>
      <svg className="curve-svg" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <polygon points={area} fill="var(--accent)" fillOpacity={0.08} />
        <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        {tenors.map((_, i) => (
          <circle key={i} cx={x(i)} cy={y(yields[i])} r={1.1} fill="var(--accent)" />
        ))}
      </svg>
      <div className="curve-axis">
        {tenors.map((t, i) => (
          <div key={i} className="curve-tick">
            <span className="ct-yield">{yields[i].toFixed(2)}</span>
            <span className="ct-tenor">{label(t)}</span>
          </div>
        ))}
      </div>
    </>
  );
}
