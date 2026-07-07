import { ExchangeTerminal } from './components/ExchangeTerminal';

// The app is now one deep thing: a live matching engine. Everything else (the OMS, RFQ, equity
// research surfaces) is archived in the repo but no longer routed — the front end is the exchange.
export default function App() {
  return <ExchangeTerminal />;
}
