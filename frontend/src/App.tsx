import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import type { Security } from './api/types';
import { Blotter } from './components/Blotter';
import { OrderTicket } from './components/OrderTicket';
import { Positions } from './components/Positions';
import { usePolling } from './hooks/usePolling';

const PORTFOLIO = 'PORT-DEMO';

export default function App() {
  const [securities, setSecurities] = useState<Security[]>([]);
  const [secError, setSecError] = useState<string | null>(null);

  const orders = usePolling(api.orders, 2000);
  const positions = usePolling(useCallback(() => api.positions(PORTFOLIO), []), 2000);

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
        <div className="status-strip">
          <span className={`dot ${connected ? 'live' : 'down'}`} />
          {connected ? 'Live · auto-refresh 2s' : 'Backend unreachable'}
          <span className="portfolio-tag">{PORTFOLIO}</span>
        </div>
      </header>

      {secError && (
        <div className="banner err global">
          Cannot reach the API at <code>/api</code>. Is the backend running on :8080?
        </div>
      )}

      <main className="layout">
        <aside className="sidebar">
          <OrderTicket securities={securities} portfolio={PORTFOLIO} onSubmitted={refresh} />
        </aside>
        <section className="content">
          <Blotter orders={orders.data ?? []} onChanged={refresh} />
          <Positions positions={positions.data ?? []} />
        </section>
      </main>
    </div>
  );
}
