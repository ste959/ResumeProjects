import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Catalysts, NewsItem, Screener, ScreenerRow, Sector, Technicals } from '../api/types';

// Exploration — market research off the Alpaca feed: a real screener (most-active / movers), server-
// computed technicals for a selected name, a sector-ETF rotation heatmap, the live news feed, and a
// catalyst rail (FOMC schedule + market calendar). Pick a name in the screener to drive the panels.

const pct = (n: number | null | undefined, dp = 2) => (n == null ? '—' : (n >= 0 ? '+' : '') + (n * 100).toFixed(dp) + '%');
const pctRaw = (n: number | null | undefined, dp = 2) => (n == null ? '—' : (n >= 0 ? '+' : '') + n.toFixed(dp) + '%');
const money = (n: number | null | undefined) => (n == null ? '—' : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const compact = (n: number | null | undefined) => (n == null ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n));
const cls = (n: number | null | undefined) => (n == null || n === 0 ? '' : n > 0 ? 'pos' : 'neg');

type SView = 'most_active' | 'gainers' | 'losers';

export function ExplorationTab() {
  const [screener, setScreener] = useState<Screener | null>(null);
  const [sview, setSview] = useState<SView>('gainers');
  const [symbol, setSymbol] = useState('AAPL');
  const [tech, setTech] = useState<Technicals | null>(null);
  const [sectors, setSectors] = useState<Sector[] | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsScope, setNewsScope] = useState<'market' | 'symbol'>('market');
  const [cat, setCat] = useState<Catalysts | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.mktScreener().then(setScreener).catch(() => setErr('market data unavailable'));
    api.mktSectors().then(setSectors).catch(() => {});
    api.mktCatalysts().then(setCat).catch(() => {});
  }, []);

  useEffect(() => { api.mktTechnicals(symbol).then(setTech).catch(() => setTech(null)); }, [symbol]);

  const loadNews = useCallback(() => {
    api.mktNews(newsScope === 'symbol' ? symbol : '', 20).then(setNews).catch(() => {});
  }, [newsScope, symbol]);
  useEffect(() => { loadNews(); }, [loadNews]);

  const rows: ScreenerRow[] = screener ? screener[sview] : [];

  if (err && !screener) {
    return <main className="live-main"><div className="live-loading">{err}</div></main>;
  }

  return (
    <main className="live-main">
      <div className="live-intro"><span className="dot live" /> Exploration — screener · technicals · sectors · news · catalysts, live off Alpaca</div>

      {cat && <CatalystRail cat={cat} />}

      <div className="xp-grid">
        {/* screener */}
        <section className="live-card xp-screener">
          <div className="xp-seg">
            {(['gainers', 'losers', 'most_active'] as SView[]).map((v) => (
              <button key={v} className={v === sview ? 'on' : ''} onClick={() => setSview(v)}>
                {v === 'most_active' ? 'Active' : v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          <div className="tablewrap">
            <table className="data-table xp-table">
              <thead><tr><th>Symbol</th><th className="r">Price</th><th className="r">{sview === 'most_active' ? 'Volume' : 'Change'}</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol} className={r.symbol === symbol ? 'row-hi' : ''} onClick={() => setSymbol(r.symbol)} style={{ cursor: 'pointer' }}>
                    <td className="mono b">{r.symbol}</td>
                    <td className="r mono">{money(r.price)}</td>
                    <td className={`r mono ${sview === 'most_active' ? 'dim' : cls(r.percent_change)}`}>
                      {sview === 'most_active' ? compact(r.volume) : pctRaw(r.percent_change)}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={3} className="dim" style={{ padding: 16 }}>no data (market may be closed)</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* technicals */}
        <section className="live-card xp-tech">
          {tech && tech.ok ? <TechPanel t={tech} /> : <div className="live-loading">no technicals for {symbol}</div>}
        </section>
      </div>

      <div className="xp-grid">
        {/* sectors */}
        <section className="live-card xp-sectors">
          <div className="live-card-head"><h3>Sector rotation</h3><span>SPDR sector ETFs · last daily move</span></div>
          <div className="xp-heat">
            {(sectors ?? []).map((s) => (
              <div key={s.symbol} className="xp-tile" style={{ background: heatColor(s.change) }} title={`${s.name} ${pct(s.change)}`}>
                <span className="xp-tile-sym">{s.symbol}</span>
                <span className="xp-tile-chg">{pct(s.change, 1)}</span>
                <span className="xp-tile-name">{s.name}</span>
              </div>
            ))}
            {!sectors && <div className="live-loading">loading sectors…</div>}
          </div>
        </section>

        {/* news */}
        <section className="live-card xp-news">
          <div className="live-card-head">
            <h3>News</h3>
            <div className="xp-seg sm">
              <button className={newsScope === 'market' ? 'on' : ''} onClick={() => setNewsScope('market')}>Market</button>
              <button className={newsScope === 'symbol' ? 'on' : ''} onClick={() => setNewsScope('symbol')}>{symbol}</button>
            </div>
          </div>
          <ul className="xp-newslist">
            {news.map((n) => (
              <li key={n.id}>
                <a href={n.url} target="_blank" rel="noreferrer">{n.headline}</a>
                <div className="xp-news-meta">
                  <span>{n.source}</span><span>{timeAgo(n.created_at)}</span>
                  {n.symbols.slice(0, 4).map((s) => <span key={s} className="xp-news-sym" onClick={() => setSymbol(s)}>{s}</span>)}
                </div>
              </li>
            ))}
            {news.length === 0 && <li className="dim">no headlines</li>}
          </ul>
        </section>
      </div>
    </main>
  );
}

function TechPanel({ t }: { t: Technicals }) {
  return (
    <>
      <div className="xp-tech-head">
        <div>
          <h3>{t.symbol}</h3>
          <span className={`xp-trend ${t.trend ? 'up' : 'down'}`}>{t.trend ? '▲ uptrend' : '▼ downtrend'} · SMA20 vs SMA50</span>
        </div>
        <div className="xp-last">
          <b>{money(t.last)}</b>
          <span className={cls(t.ret_1w)}>{pct(t.ret_1w)} 1w</span>
        </div>
      </div>
      <Spark data={t.spark ?? []} up={(t.ret_1m ?? 0) >= 0} />
      <div className="xp-ind">
        <Ind label="SMA 20" value={money(t.sma20)} />
        <Ind label="SMA 50" value={money(t.sma50)} />
        <Ind label="RSI 14" value={t.rsi14 == null ? '—' : t.rsi14.toFixed(0)} tone={t.rsi14 == null ? undefined : t.rsi14 > 70 ? 'bad' : t.rsi14 < 30 ? 'good' : undefined} />
        <Ind label="ATR %" value={pct(t.atr_pct, 1)} />
        <Ind label="1M return" value={pct(t.ret_1m)} tone={cls(t.ret_1m) as 'good' | 'bad' | ''} />
        <Ind label="3M return" value={pct(t.ret_3m)} tone={cls(t.ret_3m) as 'good' | 'bad' | ''} />
        <Ind label="Range hi" value={money(t.hi)} />
        <Ind label="Range lo" value={money(t.lo)} />
      </div>
      <p className="xp-tech-foot">{t.n} daily bars · indicators computed server-side from real bars</p>
    </>
  );
}

function Ind({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' | '' }) {
  return <div className="xp-indcell"><span>{label}</span><b className={tone || ''}>{value}</b></div>;
}

function CatalystRail({ cat }: { cat: Catalysts }) {
  const chips: { label: string; sub: string; kind: string }[] = [];
  const next = cat.fomc[0];
  if (next) chips.push({ label: 'FOMC decision', sub: `${fmtDate(next.date)} · in ${next.days_out}d`, kind: 'fomc' });
  if (cat.next_holiday) chips.push({ label: 'Market holiday', sub: `${fmtDate(cat.next_holiday.date)} · in ${cat.next_holiday.days_out}d`, kind: 'hol' });
  if (cat.next_early_close) chips.push({ label: 'Early close', sub: `${fmtDate(cat.next_early_close.date)} · ${cat.next_early_close.close}`, kind: 'early' });
  cat.fomc.slice(1, 4).forEach((f) => chips.push({ label: 'FOMC', sub: `${fmtDate(f.date)} · in ${f.days_out}d`, kind: 'fomc2' }));
  return (
    <div className="xp-rail">
      <span className="xp-rail-title">Catalysts</span>
      {chips.map((c, i) => (
        <div key={i} className={`xp-chip k-${c.kind}`}><b>{c.label}</b><span>{c.sub}</span></div>
      ))}
    </div>
  );
}

function Spark({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return <div className="xp-spark-empty" />;
  const W = 560, H = 90;
  const lo = Math.min(...data), hi = Math.max(...data);
  const x = (i: number) => (i / (data.length - 1)) * W;
  const y = (v: number) => H - ((v - lo) / (hi - lo || 1)) * (H - 8) - 4;
  const line = data.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const color = up ? 'var(--buy)' : 'var(--sell)';
  return (
    <svg className="xp-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="price sparkline">
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function heatColor(chg: number | null): string {
  if (chg == null) return 'var(--panel-2)';
  const a = Math.min(0.5, Math.abs(chg) * 18);
  return chg >= 0 ? `color-mix(in srgb, var(--buy) ${a * 100}%, var(--panel))` : `color-mix(in srgb, var(--sell) ${a * 100}%, var(--panel))`;
}
function fmtDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
function timeAgo(iso: string): string {
  if (!iso) return '';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
