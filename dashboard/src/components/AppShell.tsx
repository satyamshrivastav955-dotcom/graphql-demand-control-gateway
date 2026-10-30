import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Activity, ChevronsLeft, ChevronsRight, FlaskConical, Home, LayoutDashboard, Menu, ScrollText, Search, Terminal, X } from 'lucide-react';
import { SignOutButton } from './AuthGate';
import CommandPalette from './CommandPalette';
import { api } from '../api/client';
import { EnforcementContext } from '../hooks/enforcement';
import { useApi } from '../hooks/useApi';
import { GatewayStatus, Wordmark } from './Brand';
import { ShadowBanner } from './ui/ShadowBanner';

const NAV = [
  { to: '/app', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/app/analyze', label: 'Analyze', icon: Terminal, end: false },
  { to: '/app/events', label: 'Events', icon: Activity, end: false },
  { to: '/app/policies', label: 'Policies', icon: ScrollText, end: false },
  { to: '/app/evaluation', label: 'Evaluation', icon: FlaskConical, end: false },
];

const COLLAPSE_KEY = 'sentinel.railCollapsed';
const isMac = typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent || '');

function NavItems({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Primary" className="space-y-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          title={collapsed ? label : undefined}
          className={({ isActive }) =>
            `group relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors ${collapsed ? 'justify-center px-0' : ''} ${
              isActive ? 'bg-white/[0.08] text-ink-50' : 'text-ink-300 hover:bg-white/[0.05] hover:text-ink-50'
            }`
          }
        >
          <Icon className="h-4 w-4 shrink-0" aria-hidden />
          <span className={collapsed ? 'sr-only' : ''}>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export default function AppShell() {
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === '1';
    } catch {
      return false;
    }
  });
  const config = useApi((s) => api.config(s), [], 60000);
  const enforcement = config.data?.enforcement;
  const { pathname } = useLocation();
  useEffect(() => setDrawer(false), [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1');
      } catch {
        /* preference just isn't remembered */
      }
      return !c;
    });
  }, []);

  return (
    <div className={`min-h-screen bg-ink-950 ${collapsed ? 'lg:grid lg:grid-cols-[56px_1fr]' : 'lg:grid lg:grid-cols-[216px_1fr]'}`}>
      <aside aria-label="Sidebar" className="sticky top-0 hidden h-screen flex-col border-r border-line bg-ink-950 px-2.5 py-3 lg:flex">
        <div className={`flex h-9 items-center ${collapsed ? 'justify-center' : 'px-1.5'}`}>
          {collapsed ? <Wordmark label="" /> : <Wordmark />}
        </div>
        <div className="mt-4">
          <NavItems collapsed={collapsed} />
        </div>
        <div className="mt-auto space-y-0.5 text-[12.5px] text-ink-400">
          <NavLink to="/" title="Landing page" className={`flex h-8 items-center gap-2.5 rounded-md px-2.5 hover:bg-white/[0.05] hover:text-ink-100 ${collapsed ? 'justify-center px-0' : ''}`}>
            <Home className="h-4 w-4 shrink-0" aria-hidden />
            <span className={collapsed ? 'sr-only' : ''}>Landing page</span>
          </NavLink>
          <div className={collapsed ? 'flex justify-center' : 'px-2.5'}>
            <SignOutButton compact={collapsed} />
          </div>
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className={`flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 hover:bg-white/[0.05] hover:text-ink-100 ${collapsed ? 'justify-center px-0' : ''}`}
          >
            {collapsed ? <ChevronsRight className="h-4 w-4" aria-hidden /> : <ChevronsLeft className="h-4 w-4" aria-hidden />}
            <span className={collapsed ? 'sr-only' : ''}>Collapse</span>
          </button>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-line bg-ink-950/80 px-3 backdrop-blur-md lg:px-5">
          <button className="btn-ghost -ml-1 h-8 w-8 px-0 lg:hidden" aria-label="Open navigation" aria-expanded={drawer} onClick={() => setDrawer(true)}>
            <Menu className="h-4 w-4" />
          </button>
          <div className="lg:hidden">
            <Wordmark to="/app" />
          </div>
          <button
            type="button"
            onClick={() => setPalette(true)}
            className="ml-auto flex h-8 items-center gap-2 rounded-md border border-line-strong bg-ink-900 px-2.5 text-[12.5px] text-ink-400 transition-colors hover:border-white/25 hover:text-ink-200 lg:ml-0 lg:w-72"
          >
            <Search className="h-3.5 w-3.5" aria-hidden />
            <span className="sr-only lg:not-sr-only lg:flex-1 lg:text-left">Search or jump to…</span>
            <span aria-hidden className="kbd hidden lg:inline-flex">{isMac ? '⌘' : 'Ctrl'}</span>
            <span aria-hidden className="kbd hidden lg:inline-flex">K</span>
          </button>
          <div className="hidden lg:ml-auto lg:block">
            <GatewayStatus />
          </div>
          <div className="lg:hidden">
            <GatewayStatus compact />
          </div>
        </header>

        {drawer && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
            <button className="absolute inset-0 animate-fade-in bg-black/70" aria-label="Close navigation" onClick={() => setDrawer(false)} />
            <div className="relative h-full w-64 animate-fade-in border-r border-line bg-ink-950 px-3 py-4">
              <div className="mb-5 flex items-center justify-between px-1.5">
                <Wordmark to="/app" />
                <button className="btn-ghost h-8 w-8 px-0" aria-label="Close navigation" onClick={() => setDrawer(false)}>
                  <X className="h-4 w-4" />
                </button>
              </div>
              <NavItems onNavigate={() => setDrawer(false)} />
            </div>
          </div>
        )}

        {enforcement === 'shadow' && <ShadowBanner />}

        <main className="mx-auto w-full max-w-[1240px] px-4 py-6 lg:px-6">
          <EnforcementContext.Provider value={enforcement}>
            <div key={pathname} className="animate-fade-in">
              <Outlet />
            </div>
          </EnforcementContext.Provider>
        </main>
      </div>

      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}
