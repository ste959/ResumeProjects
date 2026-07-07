import { Link } from 'react-router-dom';

// The portfolio front door: three independent systems, each its own self-contained product. A
// reviewer picks one and walks into a focused app — no mashed-together nav.

interface Project {
  to: string;
  eyebrow: string;
  title: string;
  pitch: string;
  stat: string;
  tags: string[];
  accent: string;
  flagship?: boolean;
}

const PROJECTS: Project[] = [
  {
    to: '/exchange',
    eyebrow: 'Market microstructure · systems',
    title: 'Matching Engine',
    pitch: 'A price-time-priority central limit order book with an Avellaneda–Stoikov market maker and agent order flow, live on a real-BTC-anchored feed. Order-by-order book, animated matches, and the analytics owning the matching makes possible — adverse selection, markouts, maker P&L attribution.',
    stat: '~2M orders/sec · p50 ~300ns matching',
    tags: ['Java', 'WebSocket', 'CLOB', 'market making'],
    accent: 'var(--a-exchange)',
    flagship: true,
  },
  {
    to: '/oms',
    eyebrow: 'Fixed income · trading systems',
    title: 'Fixed-Income Desk',
    pitch: 'An order-management system that models how bonds actually trade: a dealer request-for-quote auction with best-execution, yield-curve pricing, bond analytics (YTM · duration · DV01 · convexity), an electronic order path, and lot-level after-tax P&L.',
    stat: 'RFQ best-ex · curve pricing · §475(f) tax lots',
    tags: ['Spring Boot', 'Postgres', 'Kafka', 'OMS'],
    accent: 'var(--a-oms)',
  },
  {
    to: '/research',
    eyebrow: 'Quant desk · research → live',
    title: 'Quant Desk',
    pitch: 'A full research pipeline wired to a real Alpaca paper account: explore the market, backtest a signal, then promote it to a live strategy trading paper money — with per-strategy P&L you can watch. One signal, traced from idea to fill.',
    stat: 'live paper trading · Alpaca',
    tags: ['Python', 'FastAPI', 'Alpaca', 'React'],
    accent: 'var(--a-research)',
  },
];

export function Landing() {
  return (
    <div className="hub">
      <header className="hub-head">
        <span className="hub-mark">◆</span>
        <h1>Quant Trading Systems</h1>
        <p>Three independent builds — a matching engine, a fixed-income OMS, and a quant-research pipeline. Each is its own self-contained system; pick one to explore.</p>
      </header>

      <div className="hub-grid">
        {PROJECTS.map((p) => (
          <Link key={p.to} to={p.to} className={`hub-card ${p.flagship ? 'flagship' : ''}`} style={{ ['--card' as string]: p.accent }}>
            <span className="hub-eyebrow">{p.eyebrow}{p.flagship && <span className="hub-flag">flagship</span>}</span>
            <h2>{p.title}</h2>
            <p className="hub-pitch">{p.pitch}</p>
            <div className="hub-stat">{p.stat}</div>
            <div className="hub-tags">{p.tags.map((t) => <span key={t}>{t}</span>)}</div>
            <span className="hub-enter">Enter <span className="hub-arrow">→</span></span>
          </Link>
        ))}
      </div>

      <footer className="hub-foot">
        The written research note lives at <code>research/RESEARCH-NOTE.md</code>; each system is documented in its own README.
      </footer>
    </div>
  );
}
