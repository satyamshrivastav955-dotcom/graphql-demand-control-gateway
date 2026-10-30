import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { SentinelEvent } from '../api/types';
import { decisionLabel, fmtDateTime, fmtMs, isShadow, snippet } from '../lib';
import { DecisionBadge, ScoreBar, TierBadge } from './ui/badges';

function typingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable;
}

/**
 * Dense event table. Rows are 32px, numbers are tabular, and the list is keyboard driven:
 * j / k (or the arrow keys) move the selection, Enter opens the event.
 */
export default function EventsTable({ events, compact = false }: { events: SentinelEvent[]; compact?: boolean }) {
  const nav = useNavigate();
  const open = useCallback((id: string) => nav(`/app/events/${encodeURIComponent(id)}`), [nav]);
  const [sel, setSel] = useState(0);
  const rows = useRef<(HTMLTableRowElement | null)[]>([]);

  useEffect(() => setSel((s) => Math.min(s, Math.max(0, events.length - 1))), [events.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typingTarget(e.target) || document.querySelector('[aria-modal="true"]')) return;
      const down = e.key === 'j' || e.key === 'ArrowDown';
      const up = e.key === 'k' || e.key === 'ArrowUp';
      if (!down && !up) return;
      // arrow keys only when focus is already inside the table, so the page can still scroll
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !(e.target as HTMLElement)?.closest?.('table')) return;
      e.preventDefault();
      setSel((s) => {
        const next = Math.max(0, Math.min(events.length - 1, s + (down ? 1 : -1)));
        rows.current[next]?.focus();
        return next;
      });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [events.length]);

  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Events table">
      <table className="w-full min-w-[680px] border-collapse">
        <thead className="sticky top-0 z-10 bg-ink-900">
          <tr className="border-b border-line">
            <th className="th w-[104px]">Time</th>
            <th className="th w-[132px]">Decision</th>
            <th className="th w-[118px]">Risk</th>
            <th className="th">Operation</th>
            {!compact && <th className="th w-[120px]">Client</th>}
            {!compact && <th className="th w-[84px] text-right">Analysis</th>}
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr
              key={e.id}
              ref={(el) => {
                rows.current[i] = el;
              }}
              tabIndex={i === sel ? 0 : -1}
              onClick={() => open(e.id)}
              onFocus={() => setSel(i)}
              onKeyDown={(k) => (k.key === 'Enter' || k.key === ' ') && (k.preventDefault(), open(e.id))}
              className={`h-8 cursor-pointer border-b border-line-faint transition-colors last:border-0 hover:bg-white/[0.04] focus-visible:bg-white/[0.06] focus-visible:outline-offset-[-2px] ${i === sel ? 'bg-white/[0.025]' : ''}`}
              aria-label={`Event ${decisionLabel(e.decision, isShadow(e.enforced))} ${snippet(e.query, 40)}`}
              aria-selected={i === sel}
            >
              <td className="td num whitespace-nowrap text-ink-400">{fmtDateTime(e.timestamp)}</td>
              <td className="td">
                <DecisionBadge decision={e.decision} size="sm" shadow={isShadow(e.enforced)} />
              </td>
              <td className="td">
                <div className="flex items-center gap-2">
                  <span className="num w-7 text-right text-[12.5px] text-ink-100">{e.score == null ? '–' : Math.round(e.score)}</span>
                  <div className="w-12">{e.score != null && e.risk_tier ? <ScoreBar score={e.score} tier={e.risk_tier} /> : null}</div>
                  <span className="hidden xl:inline">{e.risk_tier ? <TierBadge tier={e.risk_tier} /> : null}</span>
                </div>
              </td>
              <td className="td max-w-0">
                <div className="flex items-baseline gap-2.5">
                  <span className="shrink-0 text-[12px] text-ink-400">{e.operation_name ?? e.operation_type ?? '—'}</span>
                  <span className="truncate font-mono text-[12px] text-ink-200">{snippet(e.query, 110)}</span>
                </div>
              </td>
              {!compact && <td className="td truncate text-ink-300">{e.client_id}</td>}
              {!compact && <td className="td num text-right text-ink-300">{fmtMs(e.latency_ms)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
