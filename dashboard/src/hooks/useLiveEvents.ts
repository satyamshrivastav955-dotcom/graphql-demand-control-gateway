import { useEffect, useState } from 'react';
import { authHeaders, clearToken, signalAuthRequired } from '../api/auth';
import { liveUrl } from '../api/client';
import type { SentinelEvent } from '../api/types';

export type LiveStatus = 'off' | 'connecting' | 'live' | 'error';

/**
 * Subscribes to the gateway's server-sent-event stream while `enabled`.
 * Uses fetch (not EventSource) so the Authorization header can be sent.
 * Events received after subscription accumulate in `fresh`; `clear()` resets them.
 */
export function useLiveEvents(enabled: boolean) {
  const [fresh, setFresh] = useState<SentinelEvent[]>([]);
  const [status, setStatus] = useState<LiveStatus>('off');

  useEffect(() => {
    if (!enabled) {
      setStatus('off');
      return;
    }
    if (typeof fetch === 'undefined' || typeof TextDecoder === 'undefined') {
      setStatus('error');
      return;
    }
    const ctrl = new AbortController();
    setStatus('connecting');

    const handleFrame = (frame: string) => {
      const data = frame
        .split('\n')
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trimStart())
        .join('\n');
      if (!data) return;
      try {
        const ev = JSON.parse(data) as SentinelEvent;
        setStatus('live');
        setFresh((prev) => [ev, ...prev].slice(0, 200));
      } catch {
        /* ignore malformed frames */
      }
    };

    (async () => {
      try {
        const res = await fetch(liveUrl(), {
          headers: { Accept: 'text/event-stream', ...authHeaders() },
          signal: ctrl.signal,
        });
        if (res.status === 401) {
          clearToken();
          signalAuthRequired();
        }
        if (!res.ok || !res.body) {
          setStatus('error');
          return;
        }
        setStatus('live');
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx = buffer.indexOf('\n\n');
          while (idx >= 0) {
            handleFrame(buffer.slice(0, idx));
            buffer = buffer.slice(idx + 2);
            idx = buffer.indexOf('\n\n');
          }
        }
        setStatus('error');
      } catch (e) {
        if ((e as Error)?.name !== 'AbortError') setStatus('error');
      }
    })();

    return () => ctrl.abort();
  }, [enabled]);

  return { fresh, status, clear: () => setFresh([]) };
}
