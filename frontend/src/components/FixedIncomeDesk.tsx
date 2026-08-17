import { useMemo } from 'react';
import type { Order, Position, Security } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { BondAnalyticsPanel } from './BondAnalyticsPanel';
import { Blotter } from './Blotter';
import { OrderTicket } from './OrderTicket';
import { Positions } from './Positions';
import { RfqDesk } from './RfqDesk';
import { YieldCurvePanel } from './YieldCurvePanel';

// The Fixed Income Desk — the full picture of how a bond actually trades. Two market structures side
// by side: the OTC dealer RFQ (how bonds really trade) as the hero, and the electronic order path
// (the same order model routed to a lit book) below. Curve + analytics give the pricing context.

export function FixedIncomeDesk({ securities, orders, positions, onChanged, portfolio }: {
  securities: Security[];
  orders: Order[];
  positions: Position[];
  onChanged: () => void;
  portfolio: string;
}) {
  const { canWrite } = useAuth();
  // Bonds only for the RFQ / analytics (fall back to the whole master if asset class isn't tagged).
  const bonds = useMemo(() => {
    const fi = securities.filter((s) => s.assetClass === 'FIXED_INCOME');
    return fi.length ? fi : securities;
  }, [securities]);

  return (
    <main className="risk-main">
      <div className="risk-intro">
        <span className="dot live" />
        Bonds trade <b>OTC by dealer request-for-quote</b>, not on a lit book — the desk requests
        quotes off the benchmark curve. The same order model also routes <b>electronically</b> to a
        central limit order book.
      </div>

      <div className="fi-top">
        <YieldCurvePanel />
        <BondAnalyticsPanel bonds={bonds} />
      </div>

      <RfqDesk bonds={bonds} portfolio={portfolio} onBooked={onChanged} />

      <div className="fi-electronic">
        <div className="fi-sub-label">Electronic path · central limit order book</div>
        <div className="fi-order-grid">
          <OrderTicket securities={securities} portfolio={portfolio} canWrite={canWrite} onSubmitted={onChanged} />
          <div className="fi-order-content">
            <Blotter orders={orders} canWrite={canWrite} onChanged={onChanged} />
            <Positions positions={positions} />
          </div>
        </div>
      </div>
    </main>
  );
}
