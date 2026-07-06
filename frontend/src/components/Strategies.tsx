import { useState } from 'react';
import { api } from '../api/client';
import type { CreateStrategyRequest, StrategyView } from '../api/types';
import { usePolling } from '../hooks/usePolling';

const PRODUCTS = ['BTC-USD', 'ETH-USD', 'SOL-USD'];
const TYPES = [
  { key: 'TWAP', label: 'TWAP (execution)' },
  { key: 'POV', label: 'POV (execution)' },
  { key: 'ALMGREN_CHRISS', label: 'Almgren–Chriss (execution)' },
  { key: 'AVELLANEDA_STOIKOV', label: 'Avellaneda–Stoikov (market maker)' },
];

const usd = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
const num = (n: number | null | undefined, dp = 4) =>
  n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: dp });

export function Strategies() {
  const [type, setType] = useState('TWAP');
  const [product, setProduct] = useState('BTC-USD');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [size, setSize] = useState('0.5');
  const [slices, setSlices] = useState('10');
  const [participation, setParticipation] = useState('0.1');
  const [kappa, setKappa] = useState('0.3');
  const [gamma, setGamma] = useState('0.4');
  const [tau, setTau] = useState('60');
  const [quoteSize, setQuoteSize] = useState('0.2');
  const [error, setError] = useState<string | null>(null);

  const runs = usePolling(api.strategies, 1000);
  const isMaker = type === 'AVELLANEDA_STOIKOV';

  async function launch(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const req: CreateStrategyRequest = isMaker
      ? { type, product, gamma: Number(gamma), kappa: Number(kappa), tau: Number(tau), quoteSize: Number(quoteSize) }
      : {
          type, product, side, size: Number(size), slices: Number(slices),
          participation: type === 'POV' ? Number(participation) : undefined,
          kappa: type === 'ALMGREN_CHRISS' ? Number(kappa) : undefined,
        };
    try {
      await api.createStrategy(req);
      runs.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Launch failed');
    }
  }

  async function stop(id: string) {
    await api.stopStrategy(id);
    runs.refresh();
  }

  return (
    <div className="risk">
      <form className="ticket strat-ticket" onSubmit={launch}>
        <h2>Launch Strategy</h2>
        <div className="row">
          <label>
            Strategy
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
          </label>
          <label>
            Product
            <select value={product} onChange={(e) => setProduct(e.target.value)}>
              {PRODUCTS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
        </div>

        {!isMaker && (
          <div className="row">
            <label>
              Side
              <div className="segmented">
                {(['BUY', 'SELL'] as const).map((s) => (
                  <button type="button" key={s} className={`seg ${side === s ? 'active ' + s.toLowerCase() : ''}`}
                          onClick={() => setSide(s)}>{s}</button>
                ))}
              </div>
            </label>
            <label>Size<input type="number" step="0.0001" value={size} onChange={(e) => setSize(e.target.value)} /></label>
            <label>Slices<input type="number" step="1" value={slices} onChange={(e) => setSlices(e.target.value)} /></label>
            {type === 'POV' && (
              <label>Participation<input type="number" step="0.01" value={participation} onChange={(e) => setParticipation(e.target.value)} /></label>
            )}
            {type === 'ALMGREN_CHRISS' && (
              <label>κ (urgency)<input type="number" step="0.1" value={kappa} onChange={(e) => setKappa(e.target.value)} /></label>
            )}
          </div>
        )}

        {isMaker && (
          <div className="row">
            <label>γ (risk aversion)<input type="number" step="0.1" value={gamma} onChange={(e) => setGamma(e.target.value)} /></label>
            <label>κ (intensity)<input type="number" step="0.1" value={kappa} onChange={(e) => setKappa(e.target.value)} /></label>
            <label>τ (horizon)<input type="number" step="1" value={tau} onChange={(e) => setTau(e.target.value)} /></label>
            <label>Quote size<input type="number" step="0.01" value={quoteSize} onChange={(e) => setQuoteSize(e.target.value)} /></label>
          </div>
        )}

        <button className="submit" type="submit">Launch {type.replace('_', '–')}</button>
        {error && <div className="banner err">{error}</div>}
      </form>

      <div className="panel">
        <div className="panel-head">
          <h2>Strategy Runs</h2>
          <span className="count">{(runs.data ?? []).length} runs · live</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Status</th>
                <th className="num">Position</th>
                <th className="num">Mark</th>
                <th className="num">Total P&amp;L</th>
                <th className="num">Fills</th>
                <th>Execution TCA / Quotes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(runs.data ?? []).length === 0 && (
                <tr><td colSpan={8} className="empty">No runs yet — launch one above.</td></tr>
              )}
              {(runs.data ?? []).map((s: StrategyView) => (
                <tr key={s.id}>
                  <td>
                    <div className="sec">{s.type.replace('_', '–')}</div>
                    <div className="sec-desc">{s.product} · {s.id}</div>
                  </td>
                  <td><span className={`badge badge-${s.status === 'RUNNING' ? 'routed' : s.status === 'DONE' ? 'filled' : 'cancelled'}`}>{s.status}</span></td>
                  <td className={`num mono ${s.position < 0 ? 'sell' : 'buy'}`}>{num(s.position, 6)}</td>
                  <td className="num mono">{usd(s.markPrice)}</td>
                  <td className={`num mono ${s.totalPnl >= 0 ? 'buy' : 'sell'}`}>{usd(s.totalPnl)}</td>
                  <td className="num mono">{s.numFills}</td>
                  <td className="mono dim">
                    {s.parentSide
                      ? `${s.parentSide} ${num(s.executedSize, 4)}/${num(s.parentSize, 4)} · ${s.implementationShortfallBps ?? '—'} bps`
                      : `${usd(s.quoteBid)} / ${usd(s.quoteAsk)}`}
                  </td>
                  <td className="actions">
                    {s.status === 'RUNNING' && (
                      <button className="danger" onClick={() => stop(s.id)}>Stop</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="tca-note">
          Execution algos take liquidity (shortfall vs arrival mid); the market maker posts quotes filled when a real
          trade prints through them. All running live on the Coinbase feed.
        </div>
      </div>
    </div>
  );
}
