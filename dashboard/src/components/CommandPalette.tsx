import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, CornerDownLeft, FlaskConical, Home, LayoutDashboard, LogOut, ScrollText, Search, Send, Terminal, Copy } from 'lucide-react';
import { clearToken } from '../api/auth';
import { API_BASE, api } from '../api/client';
import { useCopy } from '../hooks/motion';
import { curlFor } from '../lib';

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: typeof Search;
  run: () => void | Promise<void>;
  keywords?: string;
}

/**
 * Ctrl/Cmd+K palette: jump to a page, search events, copy a curl for the gateway, send a test request, sign out.
 * Implemented as an ARIA combobox/listbox so it is fully keyboard and screen-reader operable.
 */
export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { copy } = useCopy();

  const go = useCallback(
    (to: string) => () => {
      nav(to);
      onClose();
    },
    [nav, onClose],
  );

  const commands = useMemo<Command[]>(() => {
    const origin = API_BASE || (typeof window !== 'undefined' ? window.location.origin : '');
    const base: Command[] = [
      { id: 'overview', label: 'Overview', hint: 'Go to', icon: LayoutDashboard, run: go('/app') },
      { id: 'analyze', label: 'Analyze an operation', hint: 'Go to', icon: Terminal, run: go('/app/analyze'), keywords: 'dry run playground editor' },
      { id: 'events', label: 'Security events', hint: 'Go to', icon: Activity, run: go('/app/events'), keywords: 'log audit requests' },
      { id: 'policies', label: 'Policies', hint: 'Go to', icon: ScrollText, run: go('/app/policies'), keywords: 'limits config tiers' },
      { id: 'evaluation', label: 'Evaluation', hint: 'Go to', icon: FlaskConical, run: go('/app/evaluation'), keywords: 'benchmark results' },
      { id: 'home', label: 'Landing page', hint: 'Go to', icon: Home, run: go('/') },
      {
        id: 'curl',
        label: 'Copy a curl for the gateway',
        hint: 'Action',
        icon: Copy,
        keywords: 'shell request',
        run: async () => {
          await copy(curlFor('{ __typename }', { origin }));
          setNote('Copied a curl command.');
        },
      },
      {
        id: 'test',
        label: 'Send a test request',
        hint: 'Action',
        icon: Send,
        keywords: 'ping typename',
        run: async () => {
          try {
            const out = await api.proxy({ query: 'query Ping { __typename }' }, 'dashboard-test');
            const sec = out.body.extensions?.security;
            setNote(sec ? `Gateway answered ${sec.decision}${sec.enforced ? ` (${sec.enforced})` : ''}.` : `Gateway answered HTTP ${out.status}.`);
          } catch (e) {
            setNote((e as Error).message);
          }
        },
      },
      {
        id: 'signout',
        label: 'Sign out',
        hint: 'Action',
        icon: LogOut,
        run: () => {
          clearToken();
          window.location.assign('/');
        },
      },
    ];
    const q = query.trim();
    const filtered = q ? base.filter((c) => `${c.label} ${c.keywords ?? ''}`.toLowerCase().includes(q.toLowerCase())) : base;
    if (q) {
      filtered.push({
        id: 'search',
        label: `Search events for “${q}”`,
        hint: 'Events',
        icon: Search,
        run: go(`/app/events?q=${encodeURIComponent(q)}`),
      });
    }
    return filtered;
  }, [query, go, copy]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
      setNote(null);
      // wait for the dialog to mount before focusing
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => setActive(0), [query]);

  if (!open) return null;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(commands.length - 1, a + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      void commands[active]?.run();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[14vh]" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKey}>
      <button className="absolute inset-0 animate-fade-in bg-black/70" aria-label="Close command palette" tabIndex={-1} onClick={onClose} />
      <div className="relative w-full max-w-[560px] animate-fade-in overflow-hidden rounded-lg border border-line-strong bg-ink-900 shadow-[0_24px_80px_-12px_rgba(0,0,0,0.9)]">
        <div className="flex items-center gap-2.5 border-b border-line px-3.5">
          <Search className="h-4 w-4 shrink-0 text-ink-400" aria-hidden />
          <input
            ref={inputRef}
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={commands[active] ? `palette-${commands[active].id}` : undefined}
            aria-label="Type a command or search events"
            className="h-12 w-full bg-transparent text-[14px] text-ink-50 placeholder:text-ink-400 focus:outline-none"
            placeholder="Jump to a page, search events, run an action…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <span className="kbd shrink-0">esc</span>
        </div>
        <ul id="palette-list" role="listbox" aria-label="Commands" className="max-h-[320px] overflow-y-auto p-1.5">
          {commands.map((c, i) => (
            <li
              key={c.id}
              id={`palette-${c.id}`}
              role="option"
              aria-selected={i === active}
              onMouseMove={() => setActive(i)}
              onClick={() => void c.run()}
              className={`flex cursor-pointer items-center gap-3 rounded-md px-2.5 py-2 text-[13.5px] ${i === active ? 'bg-white/[0.08] text-ink-50' : 'text-ink-200'}`}
            >
              <c.icon className="h-4 w-4 shrink-0 text-ink-400" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{c.label}</span>
              {c.hint && <span className="text-[12px] text-ink-400">{c.hint}</span>}
              {i === active && <CornerDownLeft className="h-3.5 w-3.5 text-ink-400" aria-hidden />}
            </li>
          ))}
          {commands.length === 0 && <li className="px-3 py-6 text-center text-[13px] text-ink-400">Nothing matches.</li>}
        </ul>
        {note && (
          <p role="status" className="border-t border-line px-3.5 py-2 text-[12.5px] text-ink-300">
            {note}
          </p>
        )}
      </div>
    </div>
  );
}
