// Backtest — Phase 4. Editable preset code snippets that run real server-side parameterized backtests
// over Alpaca history (signal → positions → cost-aware P&L → honest stats), then promote to Live.
export function BacktestTab() {
  return (
    <main className="live-main">
      <div className="live-intro"><span className="dot" /> Backtest — test a signal before it trades real paper money</div>
      <section className="live-card roadmap">
        <div className="roadmap-head"><span className="roadmap-badge">Phase 4</span><h3>From snippet to strategy</h3></div>
        <div className="roadmap-grid">
          <div className="roadmap-item"><b>Preset snippets</b><span>Editable strategy templates (momentum, mean-reversion, OFI) you tweak in place.</span></div>
          <div className="roadmap-item"><b>Real data</b><span>Runs over Alpaca historical bars — the same feed the Live account trades on.</span></div>
          <div className="roadmap-item"><b>Cost-aware</b><span>Slippage & commission modeled, so the P&L is net, not a gross fantasy.</span></div>
          <div className="roadmap-item"><b>Honest stats</b><span>Sharpe with HAC t-stat, drawdown, turnover — the same gauntlet, no cherry-picking.</span></div>
          <div className="roadmap-item"><b>Risk</b><span>Position sizing, gross/net caps, and a kill-switch before anything goes live.</span></div>
          <div className="roadmap-item"><b>Promote</b><span>A backtest that survives becomes a registered strategy on the Live desk.</span></div>
        </div>
        <p className="roadmap-foot">This closes the loop: <b>research → backtest → live</b>, one signal traced the whole way.</p>
      </section>
    </main>
  );
}
