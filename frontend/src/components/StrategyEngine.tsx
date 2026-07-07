import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { QpEngine, QpStrategy } from '../api/types';

// The live strategy engine — per-strategy P&L on the real paper account, with arm/disarm/flatten and
// a global kill switch. This is the crown jewel: every order the engine places is tagged to its
// strategy, so the account decomposes into who-bought-what and how each sleeve is performing.

const money = (n: number | null | undefined, dp = 2) =>
  n == null ? '—' : (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const sgn = (n: number | null | undefined) =>
  n == null ? '—' : (n >= 0 ? '+' : '-') + '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cls = (n: number | null | undefined) => (n == null || n === 0 ? '' : n > 0 ? 'pos' : 'neg');
const qtyf = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 6 });

export function StrategyEngine() {
  const [eng, setEng] = useState<QpEngine | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => api.qpStrategies().then((e) => { if (active) setEng(e); }).catch(() => {});
    void load();
    const id = window.setInterval(load, 5000);
    return () => { active = false; window.clearInterval(id); };
  }, []);

  const act = async (key: string, fn: () => Promise<QpEngine>) => {
    setBusy(key);
    try { setEng(await fn()); } catch { /* keep last state */ } finally { setBusy(null); }
  };

  if (!eng || !eng.configured) return null;
  const armed = new Set(eng.armed);
  const totalPnl = eng.strategies.reduce((t, s) => t + (s.total_pnl ?? 0), 0);

  return (
    <section className="live-card se">
      <div className="se-head">
        <div className="se-title">
          <h3>Strategy engine</h3>
          <span className={`se-status ${eng.running ? 'on' : 'off'}`}>
            <span className="dot" /> {eng.running ? 'running' : 'stopped'} · every {eng.interval}s
            {eng.last_run && <> · last {ago(eng.last_run)}</>}
          </span>
        </div>
        <div className="se-total">
          <span>Engine P&amp;L</span>
          <b className={cls(totalPnl)}>{sgn(totalPnl)}</b>
        </div>
        {eng.kill ? (
          <button className="se-btn resume" disabled={busy === 'kill'} onClick={() => act('kill', api.qpResume)}>Release kill</button>
        ) : (
          <button className="se-btn kill" disabled={busy === 'kill'} onClick={() => act('kill', api.qpKill)}>◼ Kill all</button>
        )}
      </div>

      {eng.kill && <div className="se-killbar">KILL ENGAGED — all strategies disarmed. Release to trade again.</div>}
      {eng.last_error && <div className="se-errbar">last cycle error: {eng.last_error}</div>}

      <div className="se-grid">
        {eng.strategies.map((s) => (
          <StrategyCard
            key={s.id} s={s} live={armed.has(s.id)} mark={eng.marks[s.symbols[0]]} busy={busy}
            onArm={() => act(s.id, () => api.qpArm(s.id))}
            onDisarm={() => act(s.id, () => api.qpDisarm(s.id))}
            onFlatten={() => act(`${s.id}-flat`, () => api.qpFlatten(s.id))}
          />
        ))}
      </div>

      <div className="se-log">
        <div className="se-log-head">Engine activity</div>
        {eng.actions.length === 0 ? (
          <div className="se-log-empty">No engine activity yet. Arm a strategy to begin trading.</div>
        ) : (
          <ul>
            {eng.actions.slice(0, 8).map((a, i) => (
              <li key={i}>
                <span className="se-log-t">{clock(a.ts)}</span>
                <span className={`se-log-k k-${a.kind}`}>{a.kind}</span>
                <span className="se-log-m">{a.msg}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function StrategyCard({ s, live, mark, busy, onArm, onDisarm, onFlatten }: {
  s: QpStrategy; live: boolean; mark: number | undefined; busy: string | null;
  onArm: () => void; onDisarm: () => void; onFlatten: () => void;
}) {
  const pos = s.positions[0];
  return (
    <div className={`se-card ${live ? 'live' : ''}`}>
      <div className="se-card-top">
        <div>
          <div className="se-card-name">{s.name}</div>
          <div className="se-card-tags">
            <span className="se-kind">{s.kind.replace('_', ' ')}</span>
            <span className="se-sym">{s.symbols.join(', ')}</span>
          </div>
        </div>
        <span className={`se-live ${live ? 'on' : ''}`}>{live ? '● LIVE' : 'idle'}</span>
      </div>

      <p className="se-desc">{s.desc}</p>

      <div className="se-metrics">
        <div className="se-metric big">
          <span>Total P&amp;L</span>
          <b className={cls(s.total_pnl)}>{sgn(s.total_pnl)}</b>
        </div>
        <div className="se-metric">
          <span>Realized</span>
          <b className={cls(s.realized)}>{sgn(s.realized)}</b>
        </div>
        <div className="se-metric">
          <span>Unrealized</span>
          <b className={cls(s.unrealized)}>{sgn(s.unrealized)}</b>
        </div>
      </div>

      <div className="se-pos">
        {pos ? (
          <>Holding <b>{qtyf(pos.qty)}</b> {pos.symbol} @ {money(pos.avg_cost)}
            <span className="se-pos-mv"> · {money(pos.market_value, 0)}</span>
            {mark != null && <span className="se-pos-mark"> · mark {money(mark)}</span>}
          </>
        ) : (
          <>Flat{mark != null && <span className="se-pos-mark"> · {s.symbols[0]} {money(mark)}</span>}
            {s.n_fills > 0 && <span className="se-pos-mv"> · {s.n_fills} fills</span>}</>
        )}
      </div>

      <div className="se-actions">
        {live ? (
          <button className="se-btn disarm" disabled={busy === s.id} onClick={onDisarm}>Disarm</button>
        ) : (
          <button className="se-btn arm" disabled={busy === s.id} onClick={onArm}>Arm</button>
        )}
        <button className="se-btn flat" disabled={!pos || busy === `${s.id}-flat`} onClick={onFlatten}>Flatten</button>
      </div>
    </div>
  );
}

function ago(epoch: number): string {
  const secs = Math.max(0, Math.round(Date.now() / 1000 - epoch));
  if (secs < 60) return `${secs}s ago`;
  return `${Math.round(secs / 60)}m ago`;
}
function clock(epoch: number): string {
  const d = new Date(epoch * 1000);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
