import { useId } from 'react';

// Plain-English glosses for the finance jargon that appears in the UI. Hover or keyboard-focus a
// dotted term to see what it means — so a reviewer who doesn't speak finance is never blocked.
// (The full version lives in docs/domain-primer.md.)
const GLOSSARY: Record<string, string> = {
  'order book': 'The live list of buy and sell offers for one instrument — a priority queue per side.',
  'matching engine': 'Pairs a new order against the best opposite orders — a merge over two sorted books.',
  spread: 'The gap between the best buy price (bid) and the best sell price (ask).',
  bid: 'The highest price someone is currently willing to buy at.',
  ask: 'The lowest price someone is currently willing to sell at.',
  'fill rate': 'The share of orders that actually got (partly) traded.',
  fill: 'A trade that (partly) completes an order.',
  position: 'How much of an instrument the desk currently holds.',
  blotter: 'The table of all orders and their status.',
  notional: 'The total dollar value of a trade or position.',
  rfq: 'Request for quote — ask several dealers for a price; the best wins (a competitive auction).',
  dv01: "A bond's dollar risk to a 1-basis-point move in interest rates.",
  'market maker': 'A bot that continuously quotes both a buy and a sell to earn the spread.',
  'alpha signal': 'A rule that scores instruments to trade — a pure function over a time-series.',
  backtest: 'Replaying history to see how a strategy would have performed (with no look-ahead).',
  sharpe: 'Return per unit of risk — higher means better risk-adjusted performance.',
  cointegration: 'A statistical test for whether two prices move together (a mean-reverting spread).',
  'stat-arb': 'Statistical arbitrage — trading the mean-reversion between related instruments.',
};

/** Inline term with an accessible tooltip gloss. Falls back to plain text if the term isn't known. */
export function Term({ children }: { children: string }) {
  const id = useId();
  const def = GLOSSARY[children.toLowerCase()];
  if (!def) return <>{children}</>;
  return (
    <span className="term" tabIndex={0} aria-describedby={id}>
      {children}
      <span className="term-tip" role="tooltip" id={id}>{def}</span>
    </span>
  );
}
