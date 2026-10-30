import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Radio, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { DECISIONS, TIERS } from '../../api/types';
import { useApi } from '../../hooks/useApi';
import { useLiveEvents } from '../../hooks/useLiveEvents';
import { TIER_STYLE } from '../../lib';
import { Async, EmptyState, PageHeader, Panel } from '../../components/ui/primitives';
import EventsTable from '../../components/EventsTable';
import FirstRun from '../../components/FirstRun';

const PAGE_SIZE = 25;

export default function Events() {
  const [params] = useSearchParams();
  const initialQ = params.get('q') ?? '';
  const [search, setSearch] = useState(initialQ);
  const [q, setQ] = useState(initialQ);
  const [decision, setDecision] = useState('');
  const [tier, setTier] = useState('');
  const [sort, setSort] = useState<'timestamp' | 'score'>('timestamp');
  const [order, setOrder] = useState<'asc' | 'desc'>('desc');
  const [offset, setOffset] = useState(0);
  const [live, setLive] = useState(false);

  // debounce free-text search
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const state = useApi((s) => api.events({ limit: PAGE_SIZE, offset, decision, tier, q, sort, order }, s), [offset, decision, tier, q, sort, order]);
  const { fresh, status, clear } = useLiveEvents(live);

  const page = state.data;
  const total = page?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);
  const filtered = Boolean(q || decision || tier);

  const refresh = () => {
    clear();
    state.reload();
  };

  return (
    <>
      <PageHeader
        title="Security events"
        description="Every request the gateway analysed, with the decision, score and the rules behind it."
        actions={
          <button
            className={live ? 'btn-primary' : 'btn-secondary'}
            aria-pressed={live}
            onClick={() => {
              setLive((l) => !l);
              clear();
            }}
          >
            <Radio className="h-3.5 w-3.5" aria-hidden />
            {live ? (status === 'error' ? 'Live (disconnected)' : status === 'connecting' ? 'Connecting…' : 'Live') : 'Go live'}
          </button>
        }
      />

      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <input
            type="search"
            aria-label="Search queries"
            className="field max-w-sm flex-1"
            placeholder="Search query text, operation, client…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select aria-label="Filter by decision" className="field w-auto" value={decision} onChange={(e) => {
              setDecision(e.target.value);
              setOffset(0);
            }}>
            <option value="">All decisions</option>
            {DECISIONS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <select aria-label="Filter by risk tier" className="field w-auto" value={tier} onChange={(e) => {
              setTier(e.target.value);
              setOffset(0);
            }}>
            <option value="">All tiers</option>
            {TIERS.map((t) => (
              <option key={t} value={t}>
                {TIER_STYLE[t].label}
              </option>
            ))}
          </select>
          <select
            aria-label="Sort order"
            className="field w-auto"
            value={`${sort}:${order}`}
            onChange={(e) => {
              const [s, o] = e.target.value.split(':');
              setSort(s as 'timestamp' | 'score');
              setOrder(o as 'asc' | 'desc');
              setOffset(0);
            }}
          >
            <option value="timestamp:desc">Newest first</option>
            <option value="timestamp:asc">Oldest first</option>
            <option value="score:desc">Highest risk first</option>
            <option value="score:asc">Lowest risk first</option>
          </select>
          {state.refreshing && <RefreshCw className="h-3.5 w-3.5 animate-spin text-ink-400" aria-label="Refreshing" />}
        </div>

        {live && fresh.length > 0 && (
          <button onClick={refresh} className="flex w-full items-center justify-center gap-2 border-b border-line bg-white/[0.05] py-2 text-[13px] text-ink-50 hover:bg-white/[0.08]">
            {fresh.length} new event{fresh.length === 1 ? '' : 's'} — refresh list
          </button>
        )}

        <Async state={state}>
          {(p) =>
            p.items.length === 0 ? (
              filtered ? (
                <EmptyState title="No events match these filters">Try clearing the search or filters.</EmptyState>
              ) : (
                <FirstRun title="No events recorded yet" onSent={state.reload} />
              )
            ) : (
              <EventsTable events={p.items} />
            )
          }
        </Async>

        {page && page.total > 0 && (
          <div className="flex items-center justify-between border-t border-line px-4 py-2 text-[13px] text-ink-300">
            <span className="num">
              {from}–{to} of {total}
            </span>
            <div className="flex items-center gap-2">
              <span className="hidden text-[12px] text-ink-400 sm:inline"><span className="kbd">j</span> <span className="kbd">k</span> move · <span className="kbd">↵</span> open</span>
              <button className="btn-secondary w-8 px-0" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} aria-label="Previous page">
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button className="btn-secondary w-8 px-0" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)} aria-label="Next page">
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </Panel>
    </>
  );
}
