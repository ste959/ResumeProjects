import { useCallback, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { ExFillView } from '../api/types';
import { usePolling } from '../hooks/usePolling';

// Market-making analytics — the breakdowns you can only compute by owning the matching engine:
// where the maker's P&L comes from (spread captured vs. adverse selection vs. inventory), where the
// latency spikes come from (deep book sweeps), and a sortable log of every fill with its markout so
// you can see which fills were profitable and under what conditions.

const usd = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(n).toFixed(2);
const bps = (n: number | null) => (n == null ? '—' : (n >= 0 ? '+' : '') + n.toFixed(2));
const ns = (n: number) => (n >= 1_000_000 ? (n / 1_000_000).toFixed(1) + 'ms' : n >= 1000 ? (n / 1000).toFixed(1) + 'µs' : n + 'ns');

type SortKey = keyof Pick<ExFillView, 'seq' | 'side' | 'price' | 'size' | 'aggressor' | 'spreadBps' | 'inventory' | 'edgeBps' | 'markoutBps'>;

export function ExchangeAnalytics() {
  const a = usePolling(api.exchangeAnalytics, 1500);
  const data = a.data;
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'seq', dir: -1 });

  const sortBy = useCallback((key: SortKey) => {
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: -1 }));
  }, []);

  const fills = useMemo(() => {
    if (!data) return [];
    const rows = [...data.fills];
    rows.sort((x, y) => {
      const vx = x[sort.key], vy = y[sort.key];
      if (vx == null) return 1; // nulls (unmatured markout) last
      if (vy == null) return -1;
      if (typeof vx === 'string') return String(vx).localeCompare(String(vy)) * sort.dir;
      return ((vx as number) - (vy as number)) * sort.dir;
    });
    return rows;
  }, [data, sort]);

  if (!data) return null;
  const { pnl, latency, summary } = data;
  const maxBucket = Math.max(1, ...latency.byMatchDepth.map((b) => b.p50Ns));

  return (
    <div className="xt-analytics">
      <div className="xt-an-grid">
        {/* P&L attribution */}
        <div className="xt-an-card">
          <h2>Maker P&amp;L Attribution</h2>
          <p className="xt-an-note">where the market maker's P&amp;L actually comes from — <b>total = spread captured − adverse selection + inventory</b></p>
          <div className="xt-pnl">
            <PnlTile label="Total P&L" v={pnl.totalUsd} big />
            <PnlTile label="Spread captured" v={pnl.spreadCapturedUsd} hint="quoted edge vs mid" />
            <PnlTile label="Adverse selection" v={pnl.adverseSelectionUsd} hint={`${summary.adverseFills.toLocaleString()} fills moved against it`} />
            <PnlTile label="Inventory" v={pnl.inventoryUsd} hint="open position, marked to fair" />
          </div>
          <div className="xt-an-sub">
            {summary.fills.toLocaleString()} fills · {(summary.informedShare * 100).toFixed(0)}% against informed flow ·
            avg edge {bps(summary.avgEdgeBps)} bps · avg markout {bps(summary.avgMarkoutBps)} bps
          </div>
        </div>

        {/* latency by match depth */}
        <div className="xt-an-card">
          <h2>Match Latency <span className="xt-h-sub">— where the spikes come from</span></h2>
          <div className="xt-lat-top">
            <span>p50 <b>{ns(latency.p50Ns)}</b></span>
            <span>p99 <b>{ns(latency.p99Ns)}</b></span>
            <span>max <b className="neg">{ns(latency.maxNs)}</b></span>
          </div>
          <div className="xt-lat-buckets">
            {latency.byMatchDepth.map((b) => (
              <div key={b.depth} className="xt-lat-row">
                <span className="xtl-label">{b.depth}</span>
                <div className="xtl-bar-wrap"><div className="xtl-bar" style={{ width: `${(b.p50Ns / maxBucket) * 100}%` }} /></div>
                <span className="xtl-val">{ns(b.p50Ns)}</span>
                <span className="xtl-count">{b.count.toLocaleString()}</span>
              </div>
            ))}
          </div>
          <p className="xt-an-note">{latency.note}</p>
        </div>
      </div>

      {/* sortable fill log */}
      <div className="xt-an-card xt-fills-card">
        <h2>Fill Log <span className="xt-h-sub">— every maker fill, marked out over ~2s · click a column to sort (find the most profitable / worst adverse selection)</span></h2>
        <div className="xt-fills">
          <table>
            <thead>
              <tr>
                {(['seq', 'side', 'price', 'size', 'aggressor', 'spreadBps', 'inventory', 'edgeBps', 'markoutBps'] as SortKey[]).map((k) => (
                  <th key={k} className={`${['price', 'size', 'spreadBps', 'inventory', 'edgeBps', 'markoutBps', 'seq'].includes(k) ? 'r' : ''} ${sort.key === k ? 'sorted' : ''}`} onClick={() => sortBy(k)}>
                    {COLS[k]}{sort.key === k ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fills.map((f) => (
                <tr key={f.seq} className={f.markoutBps != null && f.markoutBps < 0 ? 'adverse' : ''}>
                  <td className="r dim">#{f.seq}</td>
                  <td className={f.side === 'BUY' ? 'pos' : 'neg'}>{f.side}</td>
                  <td className="r">{'$' + Math.round(f.price).toLocaleString()}</td>
                  <td className="r">{f.size.toFixed(3)}</td>
                  <td><span className={`xt-aggr ${f.aggressor.toLowerCase()}`}>{f.aggressor}</span></td>
                  <td className="r dim">{f.spreadBps.toFixed(1)}</td>
                  <td className={`r ${f.inventory >= 0 ? 'pos' : 'neg'}`}>{f.inventory >= 0 ? '+' : ''}{f.inventory.toFixed(3)}</td>
                  <td className="r pos">{bps(f.edgeBps)}</td>
                  <td className={`r ${f.markoutBps == null ? 'dim' : f.markoutBps >= 0 ? 'pos' : 'neg'}`}>{bps(f.markoutBps)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const COLS: Record<SortKey, string> = {
  seq: '#', side: 'Side', price: 'Price', size: 'Size', aggressor: 'Aggressor',
  spreadBps: 'Spread', inventory: 'Inv (BTC)', edgeBps: 'Edge bps', markoutBps: 'Markout bps',
};

function PnlTile({ label, v, hint, big }: { label: string; v: number; hint?: string; big?: boolean }) {
  return (
    <div className={`xt-pnl-tile ${big ? 'big' : ''}`}>
      <span className="xtp-label">{label}</span>
      <span className={`xtp-value ${v >= 0 ? 'pos' : 'neg'}`}>{usd(v)}</span>
      {hint && <span className="xtp-hint">{hint}</span>}
    </div>
  );
}
