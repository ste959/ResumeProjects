import { useEffect, useState } from 'react';
import type { RatesSnapshot } from '../api/types';

// Live rates-desk market data over /ws/rates: the server pushes a full snapshot (curve, last RFQ,
// dealers, our book + risk + P&L attribution, and RFQ analytics) each tick.

function socketUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/rates`;
}

export function useRatesStream(): { connected: boolean; snapshot: RatesSnapshot | null } {
  const [connected, setConnected] = useState(false);
  const [snapshot, setSnapshot] = useState<RatesSnapshot | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;
    const connect = () => {
      if (closed) return;
      const ws = new WebSocket(socketUrl());
      ws.onopen = () => setConnected(true);
      ws.onmessage = (ev) => {
        try {
          setSnapshot(JSON.parse(ev.data) as RatesSnapshot);
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
    };
  }, []);

  return { connected, snapshot };
}
