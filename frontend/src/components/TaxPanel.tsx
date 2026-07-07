import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { TaxReport, TaxTrade } from '../api/types';

// The after-tax layer most demos skip entirely. Runs a trade sequence through the tax engine and
// shows what actually compounds: realized gain split short/long-term, wash-sale disallowance, and the
// tax bill — with the lot-selection method and tax regime switchable so the difference is visible.

// A representative sequence: two buys, a partial sell (mixes long- and short-term lots), a repurchase
// inside 30 days of a loss (a wash sale under the retail regime), then a final sell.
const SAMPLE: TaxTrade[] = [
  { time: '2023-02-01T00:00:00Z', side: 'BUY', quantity: 100, price: 150 },
  { time: '2023-08-15T00:00:00Z', side: 'BUY', quantity: 100, price: 178 },
  { time: '2024-05-20T00:00:00Z', side: 'SELL', quantity: 120, price: 168 },
  { time: '2024-06-05T00:00:00Z', side: 'BUY', quantity: 40, price: 165 },
  { time: '2024-11-01T00:00:00Z', side: 'SELL', quantity: 80, price: 196 },
];
const MARK = 200;

const LOT_METHODS = ['HIFO', 'FIFO', 'LIFO'];
const REGIMES = [
  { key: 'RETAIL', label: 'Retail (cap gains + wash)' },
  { key: 'TRADER_MTM', label: '§475(f) MTM' },
];

const money = (n: number | undefined) =>
  n == null ? '—' : (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
const pct = (n: number | undefined) => (n == null ? '—' : (n * 100).toFixed(1) + '%');

export function TaxPanel() {
  const [assetClass, setAssetClass] = useState('EQUITY');
  const [lotMethod, setLotMethod] = useState('HIFO');
  const [regime, setRegime] = useState('RETAIL');
  const [report, setReport] = useState<TaxReport | null>(null);
  const [err, setErr] = useState(false);

  const run = useCallback(() => {
    setErr(false);
    api
      .taxCompute({ assetClass, lotMethod, regime, markPrice: MARK, trades: SAMPLE })
      .then(setReport)
      .catch(() => setErr(true));
  }, [assetClass, lotMethod, regime]);

  useEffect(() => { run(); }, [run]);

  return (
    <div className="panel tax-panel">
      <div className="panel-head">
        <h2>After-Tax P&amp;L</h2>
        <span className="count">lot accounting · wash sales · §475(f)</span>
      </div>

      <div className="tax-controls">
        <Toggle label="Lot method" options={LOT_METHODS.map((m) => ({ key: m, label: m }))} value={lotMethod} onChange={setLotMethod} />
        <Toggle label="Regime" options={REGIMES} value={regime} onChange={setRegime} />
        <Toggle label="Asset" options={[{ key: 'EQUITY', label: 'Equity' }, { key: 'CRYPTO', label: 'Crypto' }]} value={assetClass} onChange={setAssetClass} />
      </div>

      {err && <div className="empty">tax engine unavailable</div>}
      {report && (
        <>
          <div className="tax-grid">
            <TaxStat label="Realized gain" value={money(report.realizedGain)} tone={report.realizedGain >= 0 ? 'good' : 'bad'} />
            <TaxStat label="Short-term" value={money(report.shortTermGain)} />
            <TaxStat label="Long-term" value={money(report.longTermGain)} hint="lower rate" />
            <TaxStat label="Wash disallowed" value={money(report.washSaleDisallowed)} tone={report.washSaleDisallowed > 0 ? 'warn' : undefined} />
            <TaxStat label="Tax owed" value={money(report.taxOwed)} tone="bad" hero />
            <TaxStat label="After-tax P&L" value={money(report.afterTaxPnl)} tone={report.afterTaxPnl >= 0 ? 'good' : 'bad'} hero />
            <TaxStat label="Effective rate" value={pct(report.effectiveTaxRate)} />
            <TaxStat label="Pre-tax P&L" value={money(report.preTaxPnl)} />
          </div>

          <div className="tablewrap">
            <table className="data-table sm tax-dispo">
              <thead>
                <tr><th>Acquired</th><th>Sold</th><th className="r">Qty</th><th className="r">Proceeds</th><th className="r">Basis</th><th className="r">Gain</th><th className="r">Held</th><th className="r">Term</th><th className="r">Wash</th></tr>
              </thead>
              <tbody>
                {report.dispositions.map((d, i) => (
                  <tr key={i}>
                    <td className="dim">{d.acquired.slice(0, 10)}</td>
                    <td className="dim">{d.sold.slice(0, 10)}</td>
                    <td className="r mono">{d.quantity}</td>
                    <td className="r mono dim">{money(d.proceeds)}</td>
                    <td className="r mono dim">{money(d.costBasis)}</td>
                    <td className={`r mono ${d.gain >= 0 ? 'pos' : 'neg'}`}>{money(d.gain)}</td>
                    <td className="r mono dim">{d.holdingDays}d</td>
                    <td className="r">{d.longTerm ? <span className="term-lt">LT</span> : <span className="term-st">ST</span>}</td>
                    <td className="r mono">{d.washDisallowed > 0 ? money(d.washDisallowed) : '—'}</td>
                  </tr>
                ))}
                {report.dispositions.length === 0 && (
                  <tr><td colSpan={9} className="empty">no dispositions (all marked-to-market)</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="tax-note">
            Same trades, switch the lot method: HIFO realizes the smallest gains (defers tax, converts
            to the long-term rate). The retail regime applies the wash-sale rule; §475(f) marks
            everything to market as ordinary income with no wash sales.
          </p>
        </>
      )}
    </div>
  );
}

function Toggle({ label, options, value, onChange }: {
  label: string; options: { key: string; label: string }[]; value: string; onChange: (v: string) => void;
}) {
  return (
    <div className="tax-toggle">
      <span className="tt-label">{label}</span>
      <div className="tt-opts">
        {options.map((o) => (
          <button key={o.key} className={o.key === value ? 'active' : ''} onClick={() => onChange(o.key)}>{o.label}</button>
        ))}
      </div>
    </div>
  );
}

function TaxStat({ label, value, hint, tone, hero }: { label: string; value: string; hint?: string; tone?: 'good' | 'bad' | 'warn'; hero?: boolean }) {
  return (
    <div className={`tax-stat ${hero ? 'hero' : ''}`}>
      <span className="ts-label">{label}</span>
      <span className={`ts-value ${tone ?? ''}`}>{value}</span>
      {hint && <span className="ts-hint">{hint}</span>}
    </div>
  );
}
