import { useEffect, useRef, useState } from 'react';
import type { ExchangeSnapshot } from '../api/types';

// Live market data from our matching engine over /ws/exchange. The server pushes a full snapshot
// (book + best-level queues + recent trades + engine stats) each tick; we also surface the set of
// prices that just traded so the book can flash the levels a match hit.

export interface ExchangeStream {
  connected: boolean;
  snapshot: ExchangeSnapshot | null;
  tradedPrices: Set<number>;
}

function socketUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/exchange`;
}

export function useExchangeStream(): ExchangeStream {
  const [state, setState] = useState<ExchangeStream>({ connected: false, snapshot: null, tradedPrices: new Set() });
  const lastSeq = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;

    const connect = () => {
      if (closed) return;
      const ws = new WebSocket(socketUrl());
      wsRef.current = ws;

      ws.onopen = () => setState((s) => ({ ...s, connected: true }));
      ws.onmessage = (ev) => {
        let snap: ExchangeSnapshot;
        try {
          snap = JSON.parse(ev.data) as ExchangeSnapshot;
        } catch {
          return;
        }
        // Prices from trades newer than the last frame → the levels to flash.
        const traded = new Set<number>();
        let maxSeq = lastSeq.current;
        for (const t of snap.trades) {
          if (t.seq > lastSeq.current) traded.add(t.price);
          if (t.seq > maxSeq) maxSeq = t.seq;
        }
        lastSeq.current = maxSeq;
        setState({ connected: true, snapshot: snap, tradedPrices: traded });
      };
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!closed) retry = window.setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      wsRef.current?.close(); // close the live socket so onmessage can't setState after unmount
    };
  }, []);

  return state;
}
