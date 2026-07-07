import { useEffect, useState } from 'react';
import { api } from '../api/client';

// The "read me first" surface: a live map of the whole platform so a reviewer sees the distributed
// system and its real status before diving into any one desk. Each service is pinged directly.

type Health = 'up' | 'down' | 'checking';
type Persona = 'core' | 'swe' | 'qr' | 'qt';

interface ServiceDef {
  key: string;
  name: string;
  persona: Persona;
  tech: string;
  role: string;
  where: string;
}

const SERVICES: ServiceDef[] = [
  { key: 'backend', name: 'OMS Backend', persona: 'core', tech: 'Java · Spring Boot',
    role: 'Order lifecycle, positions, securities master, RFQ, and reporting/TCA in hand-written SQL.',
    where: ':8080 /api' },
  { key: 'risk', name: 'Risk Service', persona: 'qt', tech: 'Java · Spring Boot',
    role: 'DV01, diversified/undiversified VaR and stress scenarios, aggregated off the Kafka order-events stream.',
    where: ':8081 /risk' },
  { key: 'research', name: 'Research Service', persona: 'qr', tech: 'Python · FastAPI',
    role: 'Factor research, the 5-layer construction stack, and live overfitting-aware backtests over the mds layer.',
    where: ':8082 /research' },
  { key: 'market', name: 'Live Market Feed', persona: 'swe', tech: 'Coinbase WS · Alpaca IEX',
    role: 'Real Level-2 depth and trade prints; paper trading against genuine liquidity with real slippage.',
    where: 'inbound WS' },
];

const PERSONA_LABEL: Record<Persona, string> = {
  core: 'Platform', swe: 'SWE — infra', qr: 'Researcher — alpha', qt: 'Trader — exec & risk',
};

export function Architecture() {
  const [health, setHealth] = useState<Record<string, { status: Health; detail: string }>>(
    Object.fromEntries(SERVICES.map((s) => [s.key, { status: 'checking', detail: 'pinging…' }])),
  );

  useEffect(() => {
    let alive = true;
    const set = (k: string, status: Health, detail: string) =>
      alive && setHealth((h) => ({ ...h, [k]: { status, detail } }));
    const check = () => {
      api.securities().then((s) => set('backend', 'up', `${s.length} securities`)).catch(() => set('backend', 'down', 'unreachable'));
      api.riskSummary().then(() => set('risk', 'up', 'streaming')).catch(() => set('risk', 'down', 'unreachable'));
      api.researchHealth()
        .then((h) => set('research', 'up', h.snapshot ? `snapshot · ${h.signals} signals` : `${h.signals} signals`))
        .catch(() => set('research', 'down', 'not started'));
      api.marketProducts().then((p) => set('market', p.length ? 'up' : 'down', `${p.length} products`)).catch(() => set('market', 'down', 'unreachable'));
    };
    check();
    const id = window.setInterval(check, 5000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);

  const upCount = Object.values(health).filter((h) => h.status === 'up').length;

  return (
    <main className="risk-main">
      <div className="risk-intro">
        <span className={`dot ${upCount > 0 ? 'live' : 'down'}`} />
        A live map of the platform — <b>{upCount} of {SERVICES.length} services up</b>. Read this
        first: the whole system at a glance, then jump into a desk.
      </div>

      {/* Data-flow pipeline: feeds → engine → OMS → {risk, research} → store */}
      <div className="panel arch-flow">
        <div className="panel-head"><h2>Data Flow</h2><span className="count">feeds → engine → OMS → risk / research</span></div>
        <div className="flow-body">
          <FlowNode label="Exchange Feeds" sub="Coinbase L2 · Alpaca IEX" persona="swe" status={health.market?.status} />
          <Arrow />
          <FlowNode label="Engine" sub="matching · execution algos" persona="swe" status={health.backend?.status} />
          <Arrow />
          <FlowNode label="OMS Core" sub="orders · positions · RFQ" persona="core" status={health.backend?.status} />
          <Arrow branch />
          <div className="flow-branch">
            <FlowNode label="Risk Service" sub="Kafka order-events → VaR" persona="qt" status={health.risk?.status} />
            <FlowNode label="Research Service" sub="warehouse → factors" persona="qr" status={health.research?.status} />
          </div>
        </div>
        <div className="flow-foot">
          Persisted to <b>Postgres</b> (Flyway) + a <b>Parquet / DuckDB</b> research warehouse ·
          events on <b>Kafka</b>. Two languages, each for the job it's best at.
        </div>
      </div>

      {/* Per-service health cards */}
      <div className="arch-grid">
        {SERVICES.map((s) => {
          const h = health[s.key];
          return (
            <div className={`panel svc-card p-${s.persona}`} key={s.key}>
              <div className="svc-head">
                <span className={`svc-dot ${h.status}`} />
                <span className="svc-name">{s.name}</span>
                <span className="svc-persona">{PERSONA_LABEL[s.persona]}</span>
              </div>
              <p className="svc-role">{s.role}</p>
              <div className="svc-foot">
                <span className="svc-tech">{s.tech}</span>
                <span className={`svc-status ${h.status}`}>
                  {h.status === 'up' ? 'LIVE' : h.status === 'down' ? 'DOWN' : '…'} · {h.detail}
                </span>
                <span className="svc-where">{s.where}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="arch-note">
        The platform demonstrates the full quant lifecycle across three personas — the{' '}
        <b className="p-swe">SWE</b> who builds the market &amp; execution infra, the{' '}
        <b className="p-qr">researcher</b> who finds the alpha, and the{' '}
        <b className="p-qt">trader</b> who executes and manages the risk. Each nav destination is one
        persona's surface.
      </div>
    </main>
  );
}

function FlowNode({ label, sub, persona, status }: { label: string; sub: string; persona: Persona; status?: Health }) {
  return (
    <div className={`flow-node p-${persona}`}>
      <div className="fn-top">
        <span className={`svc-dot ${status ?? 'checking'}`} />
        <span className="fn-label">{label}</span>
      </div>
      <span className="fn-sub">{sub}</span>
    </div>
  );
}

function Arrow({ branch = false }: { branch?: boolean }) {
  return <span className={`flow-arrow ${branch ? 'branch' : ''}`}>{branch ? '⇒' : '→'}</span>;
}
