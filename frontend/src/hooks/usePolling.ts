import { useCallback, useEffect, useRef, useState } from 'react';

interface PollingState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

/**
 * Polls an async fetcher on an interval and exposes the latest result. Used to keep
 * the blotter and positions views live as the execution simulator fills orders.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 2000): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Keep the latest fetcher without making it a dependency of the effect.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const tick = () => {
      if (active) void load();
    };
    tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [load, intervalMs]);

  return { data, error, loading, refresh: load };
}
