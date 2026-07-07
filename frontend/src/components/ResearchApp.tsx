import { useState } from 'react';
import { Link } from 'react-router-dom';
import { BacktestTab } from './BacktestTab';
import { ExplorationTab } from './ExplorationTab';
import { LiveTab } from './LiveTab';

// Quant Desk — a fresh research→backtest→live pipeline as three tabs, backed end-to-end by a real
// Alpaca paper account. Same light desk design language as the Fixed-Income product; its own identity.
type Tab = 'explore' | 'backtest' | 'live';

export function ResearchApp() {
  const [tab, setTab] = useState<Tab>('live');
  return (
    <div className="app-shell research-shell">
      <header className="shell-head">
        <Link to="/" className="shell-back">← Projects</Link>
        <div className="shell-brand">
          <span className="shell-mark">∿</span>
          <div><h1>Quant Desk</h1><p>research → backtest → live · Alpaca paper</p></div>
        </div>
        <nav className="shell-nav">
          <button className={tab === 'explore' ? 'active' : ''} onClick={() => setTab('explore')}>Exploration</button>
          <button className={tab === 'backtest' ? 'active' : ''} onClick={() => setTab('backtest')}>Backtest</button>
          <button className={tab === 'live' ? 'active' : ''} onClick={() => setTab('live')}>Live Strategies</button>
        </nav>
      </header>

      {tab === 'explore' && <ExplorationTab />}
      {tab === 'backtest' && <BacktestTab />}
      {tab === 'live' && <LiveTab />}
    </div>
  );
}
