import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import type { Security } from './api/types';
import { AnalyticsPanel } from './components/AnalyticsPanel';
import { Blotter } from './components/Blotter';
import { OrderTicket } from './components/OrderTicket';
import { Positions } from './components/Positions';
import { RiskDashboard } from './components/RiskDashboard';
import { usePolling } from './hooks/usePolling';

const PORTFOLIO = 'PORT-DEMO';

type Tab = 'trading' | 'risk' | 'analytics';

export default function App() {
  const [securities, setSecurities] = useState<Security[]>([]);
  const [secError, setSecError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('trading');

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
            <h1>BondDesk OMS</h1>
            <p>Fixed Income Order &amp; Execution Management</p>
          </div>
        </div>
        <nav className="tabs">
          <button className={tab === 'trading' ? 'active' : ''} onClick={() => setTab('trading')}>
            Trading Desk
          </button>
          <button className={tab === 'risk' ? 'active' : ''} onClick={() => setTab('risk')}>
            Risk
          </button>
          <button className={tab === 'analytics' ? 'active' : ''} onClick={() => setTab('analytics')}>
            Analytics
          </button>
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
    </div>
  );
}

/** Live ticking clock for the terminal header. */
function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return <span className="mono">{now.toLocaleTimeString('en-GB', { hour12: false })}</span>;
}
