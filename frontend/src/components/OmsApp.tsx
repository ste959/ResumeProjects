import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Security } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { usePolling } from '../hooks/usePolling';
import { AnalyticsPanel } from './AnalyticsPanel';
import { Blotter } from './Blotter';
import { LoginControl } from './LoginControl';
import { OrderTicket } from './OrderTicket';
import { Positions } from './Positions';
import { RatesTerminal } from './RatesTerminal';
import { RiskDashboard } from './RiskDashboard';
import { TaxPanel } from './TaxPanel';

// The Fixed-Income product: its flagship is a live rates dealing desk (dealer RFQ market + curve +
// key-rate risk + P&L attribution). Supporting views keep the electronic cash OMS and the risk/tax layer.
const PORTFOLIO = 'PORT-DEMO';
type Tab = 'rates' | 'cash' | 'risk';

export function OmsApp() {
  const [securities, setSecurities] = useState<Security[]>([]);
  const [tab, setTab] = useState<Tab>('rates');
  const { canWrite } = useAuth();

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
          <div><h1>Fixed-Income Desk</h1><p>rates dealing · dealer RFQ · risk &amp; tax</p></div>
        </div>
        <nav className="shell-nav">
          <button className={tab === 'rates' ? 'active' : ''} onClick={() => setTab('rates')}>Rates Desk</button>
          <button className={tab === 'cash' ? 'active' : ''} onClick={() => setTab('cash')}>Cash OMS</button>
          <button className={tab === 'risk' ? 'active' : ''} onClick={() => setTab('risk')}>Risk &amp; Tax</button>
        </nav>
        <LoginControl />
      </header>

      {tab === 'rates' && <RatesTerminal />}

      {tab === 'cash' && (
        <main className="risk-main">
          <div className="risk-intro">
            <span className="dot live" />
            Electronic order path — stage, route &amp; fill bond orders through the OMS
          </div>
          <div className="fi-order-grid">
            <OrderTicket securities={securities} portfolio={PORTFOLIO} canWrite={canWrite} onSubmitted={refresh} />
            <div className="fi-order-content">
              <Blotter orders={orders.data ?? []} canWrite={canWrite} onChanged={refresh} />
              <Positions positions={positions.data ?? []} />
            </div>
          </div>
        </main>
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
