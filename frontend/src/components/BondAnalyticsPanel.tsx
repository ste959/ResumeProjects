import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { BondAnalytics, Security } from '../api/types';

// A bond's computed analytics — yield-to-maturity, durations, convexity and DV01 — from the pricing
// engine (Newton-solved YTM off the cash flows). Shows there's real fixed-income math behind the
// "clean price" a reviewer would otherwise take on faith.

const n2 = (v: number | undefined) => (v == null ? '—' : v.toFixed(2));
const n3 = (v: number | undefined) => (v == null ? '—' : v.toFixed(3));
const money = (v: number | undefined) => (v == null ? '—' : '$' + v.toLocaleString('en-US', { maximumFractionDigits: 2 }));

export function BondAnalyticsPanel({ bonds }: { bonds: Security[] }) {
  const [cusip, setCusip] = useState('');
  const [a, setA] = useState<BondAnalytics | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    if (!cusip && bonds.length) setCusip(bonds[0].cusip);
  }, [bonds, cusip]);

  useEffect(() => {
    if (!cusip) return;
    setErr(false);
    api.bondAnalytics(cusip).then(setA).catch(() => setErr(true));
  }, [cusip]);

  return (
    <div className="panel analytics-panel">
      <div className="panel-head">
        <h2>Bond Analytics</h2>
        <select className="an-select" value={cusip} onChange={(e) => setCusip(e.target.value)}>
          {bonds.map((b) => (
            <option key={b.cusip} value={b.cusip}>{b.description}</option>
          ))}
        </select>
      </div>
      <div className="an-body">
        {err && <div className="empty">analytics unavailable</div>}
        {!err && !a && <div className="empty">loading…</div>}
        {a && (
          <>
            <div className="an-grid">
              <AnStat label="YTM" value={n3(a.yieldToMaturityPct) + '%'} hero />
              <AnStat label="Mod. Duration" value={n2(a.modifiedDuration)} />
              <AnStat label="DV01" value={money(a.dv01)} hint="per $100 face" />
              <AnStat label="Convexity" value={n2(a.convexity)} />
              <AnStat label="Clean" value={n3(a.cleanPrice)} />
              <AnStat label="Dirty" value={n3(a.dirtyPrice)} />
              <AnStat label="Accrued" value={n3(a.accruedInterest)} />
              <AnStat label="Mac. Duration" value={n2(a.macaulayDuration)} />
            </div>
            <div className="an-foot">settlement {a.settlementDate} · {a.description}</div>
          </>
        )}
      </div>
    </div>
  );
}

function AnStat({ label, value, hint, hero }: { label: string; value: string; hint?: string; hero?: boolean }) {
  return (
    <div className={`an-stat ${hero ? 'hero' : ''}`}>
      <span className="as-label">{label}</span>
      <span className="as-value">{value}</span>
      {hint && <span className="as-hint">{hint}</span>}
    </div>
  );
}
