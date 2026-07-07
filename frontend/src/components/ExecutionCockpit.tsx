import { useCallback, useState } from 'react';
import { api } from '../api/client';
import type { CreateStrategyRequest, EquityStatus, StrategyView } from '../api/types';
import { usePolling } from '../hooks/usePolling';

// The Execution cockpit — the quant trader's live desk. Crypto execution algos & a market maker run
// on the real feed with live P&L / TCA and full lifecycle control (pause · modify params in-flight ·
// kill), and the equity operational loop (target book → broker → risk caps → last rebalance) shows
// research routing to a monitored, risk-gated paper book.

const PRODUCTS = ['BTC-USD', 'ETH-USD', 'SOL-USD'];
const TYPES = [
  { key: 'TWAP', label: 'TWAP (execution)' },
  { key: 'POV', label: 'POV (execution)' },
  { key: 'ALMGREN_CHRISS', label: 'Almgren–Chriss (execution)' },
  { key: 'AVELLANEDA_STOIKOV', label: 'Avellaneda–Stoikov (maker)' },
];

const usd = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
const num = (n: number | null | undefined, dp = 4) => (n == null ? '—' : n.toFixed(dp));

export function ExecutionCockpit() {
  const runs = usePolling(api.strategies, 1000);
  const list = runs.data ?? [];

  return (
    <main className="risk-main">
      <div className="risk-intro">
        <span className="dot live" />
        Live <b>execution algos</b> (TWAP / POV / Almgren–Chriss) &amp; an <b>Avellaneda–Stoikov market
        maker</b> on the Coinbase feed — monitor, modify in-flight, and kill; with real TCA.
      </div>

      <LaunchForm onLaunched={runs.refresh} />

      <div className="cockpit-runs">
        {list.length === 0 && <div className="panel"><div className="empty" style={{ padding: '28px' }}>No runs yet — launch one above.</div></div>}
        {list.map((s) => <StrategyCard key={s.id} s={s} onChanged={runs.refresh} />)}
      </div>

      <EquityOps />
    </main>
  );
}

// ---- launch ----
function LaunchForm({ onLaunched }: { onLaunched: () => void }) {
  const [type, setType] = useState('POV');
  const [product, setProduct] = useState('BTC-USD');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [size, setSize] = useState('0.5');
  const [slices, setSlices] = useState('10');
  const [participation, setParticipation] = useState('0.1');
  const [kappa, setKappa] = useState('0.3');
  const [gamma, setGamma] = useState('0.4');
  const [tau, setTau] = useState('60');
  const [quoteSize, setQuoteSize] = useState('0.2');
  const [err, setErr] = useState<string | null>(null);
  const isMaker = type === 'AVELLANEDA_STOIKOV';

  const launch = useCallback(async () => {
    setErr(null);
    const req: CreateStrategyRequest = isMaker
      ? { type, product, gamma: Number(gamma), kappa: Number(kappa), tau: Number(tau), quoteSize: Number(quoteSize) }
      : {
          type, product, side, size: Number(size), slices: Number(slices),
          participation: type === 'POV' ? Number(participation) : undefined,
          kappa: type === 'ALMGREN_CHRISS' ? Number(kappa) : undefined,
        };
    try {
      await api.createStrategy(req);
      onLaunched();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Launch failed');
    }
  }, [type, product, side, size, slices, participation, kappa, gamma, tau, quoteSize, isMaker, onLaunched]);

  return (
    <div className="panel launch-panel">
      <div className="panel-head"><h2>Launch Strategy</h2><span className="count">live on the feed</span></div>
      <div className="launch-body">
        <label className="lf"><span>Strategy</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </label>
        <label className="lf"><span>Product</span>
          <select value={product} onChange={(e) => setProduct(e.target.value)}>{PRODUCTS.map((p) => <option key={p}>{p}</option>)}</select>
        </label>
        {!isMaker && (
          <>
            <label className="lf"><span>Side</span>
              <div className="side-toggle">
                <button className={side === 'BUY' ? 'buy active' : ''} onClick={() => setSide('BUY')}>Buy</button>
                <button className={side === 'SELL' ? 'sell active' : ''} onClick={() => setSide('SELL')}>Sell</button>
              </div>
            </label>
            <label className="lf"><span>Size</span><input type="number" step="0.0001" value={size} onChange={(e) => setSize(e.target.value)} /></label>
            <label className="lf"><span>Slices</span><input type="number" step="1" value={slices} onChange={(e) => setSlices(e.target.value)} /></label>
            {type === 'POV' && <label className="lf"><span>Participation</span><input type="number" step="0.01" value={participation} onChange={(e) => setParticipation(e.target.value)} /></label>}
            {type === 'ALMGREN_CHRISS' && <label className="lf"><span>κ urgency</span><input type="number" step="0.1" value={kappa} onChange={(e) => setKappa(e.target.value)} /></label>}
          </>
        )}
        {isMaker && (
          <>
            <label className="lf"><span>γ risk-av</span><input type="number" step="0.1" value={gamma} onChange={(e) => setGamma(e.target.value)} /></label>
            <label className="lf"><span>κ intensity</span><input type="number" step="0.1" value={kappa} onChange={(e) => setKappa(e.target.value)} /></label>
            <label className="lf"><span>τ horizon</span><input type="number" step="1" value={tau} onChange={(e) => setTau(e.target.value)} /></label>
            <label className="lf"><span>Quote size</span><input type="number" step="0.01" value={quoteSize} onChange={(e) => setQuoteSize(e.target.value)} /></label>
          </>
        )}
        <button className="launch-btn" onClick={launch}>Launch</button>
      </div>
      {err && <div className="rfq-err">{err}</div>}
    </div>
  );
}

// ---- one running strategy ----
function StrategyCard({ s, onChanged }: { s: StrategyView; onChanged: () => void }) {
  const [showMod, setShowMod] = useState(false);
  const active = s.status === 'RUNNING' || s.status === 'PAUSED';
  const canModify = s.type === 'POV' || s.type === 'AVELLANEDA_STOIKOV';
  const isMaker = s.type === 'AVELLANEDA_STOIKOV';
  const progress = s.parentSize && s.parentSize > 0 && s.executedSize != null
    ? Math.min(100, (s.executedSize / s.parentSize) * 100) : null;

  const act = useCallback(async (fn: () => Promise<unknown>) => { await fn(); onChanged(); }, [onChanged]);

  return (
    <div className={`panel strat-card st-${s.status.toLowerCase()}`}>
      <div className="sc-head">
        <div className="sc-id">
          <span className="sc-type">{s.type.replace(/_/g, '–')}</span>
          <span className="sc-meta">{s.product} · {s.id}</span>
        </div>
        <span className={`sc-badge ${s.status.toLowerCase()}`}>{s.status}</span>
      </div>

      {progress != null ? (
        <div className="sc-progress">
          <div className="scp-bar"><div className={`scp-fill ${s.parentSide?.toLowerCase()}`} style={{ width: `${progress}%` }} /></div>
          <div className="scp-label">
            {s.parentSide} {num(s.executedSize)} / {num(s.parentSize)} ({progress.toFixed(0)}%) ·
            IS <b className={(s.implementationShortfallBps ?? 0) <= 0 ? 'pos' : 'neg'}>{s.implementationShortfallBps ?? '—'} bps</b>
          </div>
        </div>
      ) : isMaker ? (
        <div className="sc-quotes">
          <span className="scq bid">bid {usd(s.quoteBid)}</span>
          <span className="scq ask">ask {usd(s.quoteAsk)}</span>
          <span className="scq inv">inv {num(s.position)}</span>
        </div>
      ) : null}

      <div className="sc-stats">
        <SC label="Position" value={num(s.position, 4)} tone={s.position < 0 ? 'bad' : s.position > 0 ? 'good' : undefined} />
        <SC label="Mark" value={usd(s.markPrice)} />
        <SC label="Total P&L" value={usd(s.totalPnl)} tone={s.totalPnl >= 0 ? 'good' : 'bad'} />
        <SC label="Realized" value={usd(s.realizedPnl)} />
        <SC label="Fills" value={String(s.numFills)} />
      </div>

      {active && (
        <div className="sc-controls">
          {s.status === 'RUNNING' && <button onClick={() => act(() => api.pauseStrategy(s.id))}>Pause</button>}
          {s.status === 'PAUSED' && <button className="resume" onClick={() => act(() => api.resumeStrategy(s.id))}>Resume</button>}
          {canModify && <button className={showMod ? 'active' : ''} onClick={() => setShowMod((v) => !v)}>Modify</button>}
          <button className="kill" onClick={() => act(() => api.stopStrategy(s.id))}>Kill</button>
        </div>
      )}

      {active && showMod && canModify && <ModifyPanel s={s} onApplied={onChanged} />}
    </div>
  );
}

function SC({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="sc-stat">
      <span className="scs-label">{label}</span>
      <span className={`scs-value ${tone ?? ''}`}>{value}</span>
    </div>
  );
}

// ---- in-flight parameter modify ----
function ModifyPanel({ s, onApplied }: { s: StrategyView; onApplied: () => void }) {
  const isPov = s.type === 'POV';
  const [participation, setParticipation] = useState(0.1);
  const [gamma, setGamma] = useState(0.4);
  const [quoteSize, setQuoteSize] = useState(0.2);

  const apply = useCallback(async () => {
    await api.modifyStrategy(s.id, isPov ? { participation } : { gamma, quoteSize });
    onApplied();
  }, [s.id, isPov, participation, gamma, quoteSize, onApplied]);

  return (
    <div className="modify-panel">
      {isPov ? (
        <label className="mp-field">
          <span>Participation: {participation.toFixed(2)}</span>
          <input type="range" min={0.01} max={1} step={0.01} value={participation} onChange={(e) => setParticipation(Number(e.target.value))} />
        </label>
      ) : (
        <>
          <label className="mp-field">
            <span>γ risk aversion: {gamma.toFixed(2)}</span>
            <input type="range" min={0.05} max={2} step={0.05} value={gamma} onChange={(e) => setGamma(Number(e.target.value))} />
          </label>
          <label className="mp-field">
            <span>Quote size: {quoteSize.toFixed(2)}</span>
            <input type="range" min={0.01} max={1} step={0.01} value={quoteSize} onChange={(e) => setQuoteSize(Number(e.target.value))} />
          </label>
        </>
      )}
      <button className="mp-apply" onClick={apply}>Apply</button>
      <span className="mp-note">applied to the live run on its next tick</span>
    </div>
  );
}

// ---- equity operational loop ----
function EquityOps() {
  const status = usePolling(api.equityStatus, 5000);
  const s = status.data as EquityStatus | null;
  const err = status.error != null;

  return (
    <div className="panel equity-ops">
      <div className="panel-head">
        <h2>Equity Operational Loop</h2>
        <span className="count">research book → broker → risk caps</span>
      </div>
      <div className="eo-body">
        {err && <div className="empty">ops status unavailable</div>}
        {!err && !s && <div className="empty">loading…</div>}
        {s && (
          <>
            <div className="eo-flow">
              <EoNode label="Target Book" ok={!!s.targetBook}
                detail={s.targetBook ? `${s.targetBook.names} names · ${s.targetBook.asOf}` : 'not loaded'} />
              <span className="eo-arrow">→</span>
              <EoNode label="Broker" ok={s.brokerReachable}
                detail={s.brokerReachable ? (s.marketOpen ? 'reachable · market open' : 'reachable · closed') : 'unreachable'} />
              <span className="eo-arrow">→</span>
              <EoNode label="Auto-Rebalance" ok={s.autoEnabled} neutral={!s.autoEnabled}
                detail={s.autoEnabled ? 'armed' : 'off (safe default)'} />
              <span className="eo-arrow">→</span>
              <EoNode label="Last Rebalance" ok={s.lastRebalance?.status === 'ROUTED'} neutral
                detail={s.lastRebalance ? `${s.lastRebalance.status} · ${s.lastRebalance.routed}/${s.lastRebalance.skipped}/${s.lastRebalance.rejected}` : 'never run'} />
            </div>

            <div className="eo-grid">
              <EoStat label="Positions" value={s.positions ? String(s.positions.count) : '—'} />
              <EoStat label="Gross long" value={money(s.positions?.grossLong)} tone="good" />
              <EoStat label="Gross short" value={money(s.positions?.grossShort)} tone="bad" />
              <EoStat label="Net exposure" value={money(s.positions?.net)} />
              <EoStat label="Desk risk cap" value={money(s.riskCaps?.desk)} />
              <EoStat label="Rebalance cap" value={money(s.riskCaps?.rebalanceBook)} />
            </div>
            <p className="eo-note">
              The rebalance <b>action</b> is gated off by default (<code>oms.rebalance.enabled=false</code>)
              and runs dry-run first — a real desk arms it deliberately. This panel is the read-only
              operational view: research target book → broker reachability &amp; market hours → risk caps →
              last run.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

const money = (n: number | null | undefined) =>
  n == null ? '—' : (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });

function EoNode({ label, detail, ok, neutral }: { label: string; detail: string; ok: boolean; neutral?: boolean }) {
  return (
    <div className={`eo-node ${neutral ? 'neutral' : ok ? 'ok' : 'down'}`}>
      <div className="eon-top"><span className="eon-dot" /><span className="eon-label">{label}</span></div>
      <span className="eon-detail">{detail}</span>
    </div>
  );
}

function EoStat({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="eo-stat">
      <span className="eos-label">{label}</span>
      <span className={`eos-value ${tone ?? ''}`}>{value}</span>
    </div>
  );
}
