import { useEffect, useRef, useState } from 'react';
import type { BookView, StreamFrame, StreamMetrics, TradePrint } from '../api/types';

// Live market-data over the backend WebSocket (/ws/market). One subscription per product; the server
// pushes book / trade / metrics frames a few times a second (a real push channel, not polling). We
// keep a rolling tape and a short metrics history for the sparklines, and auto-reconnect on drop.

const MAX_TAPE = 40;
const MAX_HISTORY = 120; // ~30s of metrics at 4 Hz

export interface MarketStream {
  connected: boolean;
  book: BookView | null;
  tape: TradePrint[];
  metrics: StreamMetrics | null;
  history: StreamMetrics[];
}

function socketUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/market`;
}

export function useMarketStream(product: string): MarketStream {
  const [connected, setConnected] = useState(false);
  const [book, setBook] = useState<BookView | null>(null);
  const [tape, setTape] = useState<TradePrint[]>([]);
  const [metrics, setMetrics] = useState<StreamMetrics | null>(null);
  const [history, setHistory] = useState<StreamMetrics[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;
    // Reset view when switching products so stale depth/tape never shows for the new one.
    setBook(null);
    setTape([]);
    setMetrics(null);
    setHistory([]);

    const connect = () => {
      if (closed) return;
      const ws = new WebSocket(socketUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        ws.send(JSON.stringify({ subscribe: product }));
      };

      ws.onmessage = (ev) => {
        let frame: StreamFrame;
        try {
          frame = JSON.parse(ev.data) as StreamFrame;
        } catch {
          return;
        }
        if (frame.product !== product) return;
        if (frame.type === 'book') {
          setBook({ product: frame.product, quote: frame.quote, bids: frame.bids, asks: frame.asks });
        } else if (frame.type === 'trade') {
          setTape((prev) => [...frame.trades.slice().reverse(), ...prev].slice(0, MAX_TAPE));
        } else if (frame.type === 'metrics') {
          setMetrics(frame.metrics);
          if (frame.metrics.ready) {
            setHistory((prev) => [...prev, frame.metrics].slice(-MAX_HISTORY));
          }
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 1500); // auto-reconnect
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [product]);

  return { connected, book, tape, metrics, history };
}
