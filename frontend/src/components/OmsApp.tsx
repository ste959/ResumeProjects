import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Security } from '../api/types';
import { usePolling } from '../hooks/usePolling';
import { AnalyticsPanel } from './AnalyticsPanel';
import { FixedIncomeDesk } from './FixedIncomeDesk';
import { RiskDashboard } from './RiskDashboard';
import { TaxPanel } from './TaxPanel';

// The Fixed-Income OMS as its own self-contained app: a dealer-RFQ trading desk and a risk/tax view,
// under its own identity header. Reuses the OMS backend endpoints (orders, RFQ, curve, analytics, tax).
const PORTFOLIO = 'PORT-DEMO';
type Tab = 'desk' | 'risk';

export function OmsApp() {
  const [securities, setSecurities] = useState<Security[]>([]);
  const [tab, setTab] = useState<Tab>('desk');

  const orders = usePolling(api.orders, 2000);
  const positions = usePolling(useCallback(() => api.positions(PORTFOLIO), []), 2000);
  const risk = usePolling(api.riskSummary, 2000);
  const deskSummary = usePolling(api.deskSummary, 3000);
  const execQuality = usePolling(api.executionQuality, 3000);
  const topSecurities = usePolling(useCallback(() => api.topSecurities(6), []), 3000);

  useEffect(() => { api.securities().then(setSecurities).catch(() => {}); }, []);
  const refresh = useCallback(() => { orders.refresh(); positions.refresh(); }, [orders, positions]);

  return (
    <div className="app-shell oms-shell">
      <header className="shell-head">
        <Link to="/" className="shell-back">← Projects</Link>
        <div className="shell-brand">
          <span className="shell-mark">▤</span>
          <div><h1>Fixed-Income Desk</h1><p>OMS · dealer RFQ · curve pricing · analytics · tax</p></div>
        </div>
        <nav className="shell-nav">
          <button className={tab === 'desk' ? 'active' : ''} onClick={() => setTab('desk')}>Trading Desk</button>
          <button className={tab === 'risk' ? 'active' : ''} onClick={() => setTab('risk')}>Risk &amp; Tax</button>
        </nav>
      </header>

      {tab === 'desk' && (
        <FixedIncomeDesk securities={securities} orders={orders.data ?? []} positions={positions.data ?? []} onChanged={refresh} portfolio={PORTFOLIO} />
      )}
      {tab === 'risk' && (
        <main className="risk-main">
          <div className="risk-intro">
            <span className={`dot ${risk.error == null ? 'live' : 'down'}`} />
            Aggregated by the <b>risk microservice</b> from the Kafka <code>order-events</code> stream
          </div>
          <RiskDashboard summary={risk.data} />
          <div className="risk-intro">
            <span className={`dot ${deskSummary.error == null ? 'live' : 'down'}`} />
            Reporting &amp; TCA in <b>hand-written SQL</b>; after-tax P&amp;L from the <b>tax engine</b>
          </div>
          <AnalyticsPanel summary={deskSummary.data} execQuality={execQuality.data ?? []} topSecurities={topSecurities.data ?? []} />
          <TaxPanel />
        </main>
      )}
    </div>
  );
}
