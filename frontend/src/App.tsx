import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import type { Security } from './api/types';
import { AnalyticsPanel } from './components/AnalyticsPanel';
import { Blotter } from './components/Blotter';
import { LiveMarket } from './components/LiveMarket';
import { OrderTicket } from './components/OrderTicket';
import { Overview } from './components/Overview';
import { Positions } from './components/Positions';
import { RiskDashboard } from './components/RiskDashboard';
import { Signals } from './components/Signals';
import { Strategies } from './components/Strategies';
import { usePolling } from './hooks/usePolling';

const PORTFOLIO = 'PORT-DEMO';

type Tab = 'overview' | 'trading' | 'risk' | 'analytics' | 'market' | 'strategies' | 'signals';

// Grouped navigation — the structure that tells the "multi-desk platform" story.
const NAV: { group: string | null; items: { key: Tab; label: string }[] }[] = [
  { group: null, items: [{ key: 'overview', label: 'Overview' }] },
  {
    group: 'Fixed Income',
    items: [
      { key: 'trading', label: 'Desk' },
      { key: 'risk', label: 'Risk' },
      { key: 'analytics', label: 'Analytics' },
    ],
  },
  {
    group: 'Live Markets',
    items: [
      { key: 'market', label: 'Market' },
      { key: 'strategies', label: 'Strategies' },
      { key: 'signals', label: 'Signals' },
    ],
  },
];

export default function App() {
  const [securities, setSecurities] = useState<Security[]>([]);
  const [secError, setSecError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('overview');

  const orders = usePolling(api.orders, 2000);
  const positions = usePolling(useCallback(() => api.positions(PORTFOLIO), []), 2000);
  const risk = usePolling(api.riskSummary, 2000);
  const deskSummary = usePolling(api.deskSummary, 3000);
  const execQuality = usePolling(api.executionQuality, 3000);
  const topSecurities = usePolling(useCallback(() => api.topSecurities(6), []), 3000);

  useEffect(() => {
    api.securities().then(setSecurities).catch((e) => setSecError(String(e)));
  }, []);

  const refresh = useCallback(() => {
    orders.refresh();
    positions.refresh();
  }, [orders, positions]);

  const connected = orders.error == null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◆</span>
          <div>
            <h1>BondDesk</h1>
            <p>Multi-Asset Trading &amp; Research Platform</p>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((section, i) => (
            <div className="nav-group" key={i}>
              {section.group && <span className="nav-group-label">{section.group}</span>}
              {section.items.map((it) => (
                <button key={it.key} className={tab === it.key ? 'active' : ''} onClick={() => setTab(it.key)}>
                  {it.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="status-strip">
          <span className={`dot ${connected ? 'live' : 'down'}`} />
          {connected ? 'LIVE' : 'OFFLINE'}
          <Clock />
          <span className="portfolio-tag">{PORTFOLIO}</span>
        </div>
      </header>

      {secError && (
        <div className="banner err global">
          Cannot reach the API at <code>/api</code>. Is the backend running on :8080?
        </div>
      )}

      {tab === 'overview' && (
        <main className="risk-main">
          <Overview onNavigate={(t) => setTab(t as Tab)} />
        </main>
      )}

      {tab === 'trading' && (
        <main className="layout">
          <aside className="sidebar">
            <OrderTicket securities={securities} portfolio={PORTFOLIO} onSubmitted={refresh} />
          </aside>
          <section className="content">
            <Blotter orders={orders.data ?? []} onChanged={refresh} />
            <Positions positions={positions.data ?? []} />
          </section>
        </main>
      )}

      {tab === 'risk' && (
        <main className="risk-main">
          <div className="risk-intro">
            <span className={`dot ${risk.error == null ? 'live' : 'down'}`} />
            Aggregated by the <b>risk microservice</b> from the Kafka <code>order-events</code> stream
          </div>
          <RiskDashboard summary={risk.data} />
        </main>
      )}

      {tab === 'analytics' && (
        <main className="risk-main">
          <div className="risk-intro">
            <span className={`dot ${deskSummary.error == null ? 'live' : 'down'}`} />
            Reporting &amp; TCA computed by the backend in <b>hand-written SQL</b> (joins, aggregates,
            window functions)
          </div>
          <AnalyticsPanel
            summary={deskSummary.data}
            execQuality={execQuality.data ?? []}
            topSecurities={topSecurities.data ?? []}
          />
        </main>
      )}

      {tab === 'market' && (
        <main className="risk-main">
          <div className="risk-intro">
            <span className="dot live" />
            Live <b>Coinbase</b> order book (real depth &amp; price action) — paper-trade against genuine
            liquidity with real slippage
          </div>
          <LiveMarket />
        </main>
      )}

      {tab === 'strategies' && (
        <main className="risk-main">
          <div className="risk-intro">
            <span className="dot live" />
            Execution algos (TWAP / POV / Almgren–Chriss) &amp; an <b>Avellaneda–Stoikov market maker</b>
            running live on the Coinbase feed, with transaction-cost analysis
          </div>
          <Strategies />
        </main>
      )}

      {tab === 'signals' && (
        <main className="risk-main">
          <div className="risk-intro">
            <span className="dot live" />
            Live <b>microstructure signals</b> from the Coinbase book — order-book imbalance, microprice
            premium, spread, and an imbalance information coefficient
          </div>
          <Signals />
        </main>
      )}
    </div>
  );
}

/** Live ticking clock for the header. */
function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return <span className="mono">{now.toLocaleTimeString('en-GB', { hour12: false })}</span>;
}
