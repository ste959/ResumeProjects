// Exploration — Phase 3. The market-research surface: screener, technicals, sectors, news, catalysts,
// all off the Alpaca backbone. Roadmap panel for now so the pipeline shape is real while Live is built out.
export function ExplorationTab() {
  return (
    <main className="live-main">
      <div className="live-intro"><span className="dot" /> Exploration — market research on the Alpaca data feed</div>
      <RoadmapCard
        phase="Phase 3"
        title="Screener · technicals · news · catalysts"
        items={[
          ['Screener', 'Most-active & top movers from Alpaca, filterable by sector, price, and momentum.'],
          ['Technicals', 'Server-computed SMA / RSI / ATR / returns per name, with a compact price panel.'],
          ['Sectors', 'A sector heatmap of breadth and returns to find where money is rotating.'],
          ['News', 'Real-time headlines from the Alpaca news feed, tagged to the symbols you follow.'],
          ['Catalysts', 'An event rail — FOMC dates, earnings, and macro releases that move the tape.'],
        ]}
      />
    </main>
  );
}

function RoadmapCard({ phase, title, items }: { phase: string; title: string; items: [string, string][] }) {
  return (
    <section className="live-card roadmap">
      <div className="roadmap-head"><span className="roadmap-badge">{phase}</span><h3>{title}</h3></div>
      <div className="roadmap-grid">
        {items.map(([k, v]) => (
          <div key={k} className="roadmap-item"><b>{k}</b><span>{v}</span></div>
        ))}
      </div>
      <p className="roadmap-foot">The backbone (Alpaca market data + news) is wired; these views fill in next.
        <b> Live Strategies</b> is being built first — it's the reason for the whole pipeline.</p>
    </section>
  );
}
