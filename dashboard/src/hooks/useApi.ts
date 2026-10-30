import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  /** True only until the first response (or failure) arrives. */
  loading: boolean;
  /** True while a background refresh is in flight. */
  refreshing: boolean;
  reload: () => void;
}

/**
 * Fetches on mount and whenever `deps` change; optionally polls.
 * Previous data is kept visible while a refresh is in flight.
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  intervalMs?: number,
): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const first = useRef(true);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    first.current = true;
    setLoading(true);
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    const ctrl = new AbortController();
    let cancelled = false;
    const run = async () => {
      if (!first.current) setRefreshing(true);
      try {
        const result = await fetcherRef.current(ctrl.signal);
        if (cancelled) return;
        setData(result);
        setError(null);
      } catch (e) {
        if (cancelled || (e as Error)?.name === 'AbortError') return;
        setError(e instanceof ApiError ? e : new ApiError((e as Error).message, 0));
      } finally {
        if (!cancelled) {
          first.current = false;
          setLoading(false);
          setRefreshing(false);
        }
      }
    };
    run();
    const id = intervalMs ? window.setInterval(run, intervalMs) : undefined;
    return () => {
      cancelled = true;
      ctrl.abort();
      if (id) window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, intervalMs]);

  return { data, error, loading, refreshing, reload };
}
