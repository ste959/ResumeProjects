import { useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { api } from './api/client';
import type { Security } from './api/types';
import { AnalyticsPanel } from './components/AnalyticsPanel';
import { Architecture } from './components/Architecture';
import { FixedIncomeDesk } from './components/FixedIncomeDesk';
import { MarketStream } from './components/MarketStream';
import { ResearchLab } from './components/ResearchLab';
import { RiskDashboard } from './components/RiskDashboard';
import { Strategies } from './components/Strategies';
import { TaxPanel } from './components/TaxPanel';
import { usePolling } from './hooks/usePolling';

const PORTFOLIO = 'PORT-DEMO';

// Navigation re-organized around the three quant personas the platform demonstrates
// (SWE builds infra · researcher finds alpha · trader executes & manages risk). Each destination is
// a "story surface" — a self-explaining view of one part of the backend, not just a function tab.
type Persona = 'core' | 'swe' | 'qr' | 'qt';
interface NavItem { path: string; label: string; persona: Persona }
const NAV: { group: string | null; items: NavItem[] }[] = [
  { group: null, items: [{ path: '/', label: 'Architecture', persona: 'core' }] },
  { group: 'Research', items: [{ path: '/research', label: 'Research Lab', persona: 'qr' }] },
  {
    group: 'Fixed Income',
    items: [
      { path: '/fixed-income', label: 'Desk', persona: 'qt' },
      { path: '/risk', label: 'Risk & TCA', persona: 'qt' },
    ],
  },
  {
    group: 'Live Markets',
    items: [
      { path: '/microstructure', label: 'Microstructure', persona: 'swe' },
      { path: '/execution', label: 'Execution', persona: 'qt' },
    ],
  },
];

function Shell() {
  const nav = useNavigate();
  const loc = useLocation();
  const [securities, setSecurities] = useState<Security[]>([]);
  const [secError, setSecError] = useState<string | null>(null);

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
                <button
                  key={it.path}
                  className={loc.pathname === it.path ? 'active' : ''}
                  data-persona={it.persona}
                  onClick={() => nav(it.path)}
                >
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

      <Routes>
        <Route path="/" element={<Architecture />} />

        <Route path="/research" element={<ResearchLab />} />

        <Route
          path="/fixed-income"
          element={
            <FixedIncomeDesk
              securities={securities}
              orders={orders.data ?? []}
              positions={positions.data ?? []}
              onChanged={refresh}
              portfolio={PORTFOLIO}
            />
          }
        />

        <Route
          path="/risk"
          element={
            <main className="risk-main">
              <div className="risk-intro">
                <span className={`dot ${risk.error == null ? 'live' : 'down'}`} />
                Aggregated by the <b>risk microservice</b> from the Kafka <code>order-events</code> stream
              </div>
              <RiskDashboard summary={risk.data} />
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
              <div className="risk-intro">
                <span className="dot live" />
                After-tax P&amp;L from the <b>tax engine</b> — lot accounting, wash sales &amp; §475(f)
                mark-to-market
              </div>
              <TaxPanel />
            </main>
          }
        />

        <Route path="/microstructure" element={<MarketStream />} />

        <Route
          path="/execution"
          element={
            <main className="risk-main">
              <div className="risk-intro">
                <span className="dot live" />
                Execution algos (TWAP / POV / Almgren–Chriss) &amp; an{' '}
                <b>Avellaneda–Stoikov market maker</b> running live on the Coinbase feed, with TCA
              </div>
              <Strategies />
            </main>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
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
