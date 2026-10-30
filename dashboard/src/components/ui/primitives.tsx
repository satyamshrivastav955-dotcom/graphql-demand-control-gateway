import { ReactNode, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';
import type { ApiError } from '../../api/client';
import { Spark } from '../charts';

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-line pb-5">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.025em] text-ink-50">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13.5px] text-ink-300">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({
  title,
  hint,
  actions,
  children,
  className = '',
}: {
  title?: string;
  hint?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="flex min-h-[44px] items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            {title && <h2 className="panel-title">{title}</h2>}
            {hint && <p className="text-[12px] text-ink-400">{hint}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/** A row of key figures in one bordered strip, separated by hairlines: not a row of cards. */
export function StatStrip({ children, cols = 4 }: { children: ReactNode; cols?: 2 | 3 | 4 }) {
  const grid = { 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3', 4: 'sm:grid-cols-2 lg:grid-cols-4' }[cols];
  return (
    <div className={`grid grid-cols-1 overflow-hidden rounded-lg border border-line bg-ink-900 [&>*]:border-b [&>*]:border-line sm:[&>*]:border-r ${grid}`}>
      {children}
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = 'default',
  source,
  trend,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: 'default' | 'allow' | 'throttle' | 'block';
  /** Short description of where the number comes from; shown as a tooltip. */
  source?: string;
  /** Recent values to draw as an inline sparkline (from real series only). */
  trend?: number[];
}) {
  const color = { default: 'text-ink-50', allow: 'text-allow', throttle: 'text-throttle', block: 'text-block' }[tone];
  const hex = { default: '#a4a7ae', allow: '#3ecf8e', throttle: '#f5a524', block: '#f5594e' }[tone];
  return (
    <div className="relative px-4 py-3.5" title={source}>
      <div className="text-[12.5px] text-ink-400">{label}</div>
      <div className="mt-1 flex items-end justify-between gap-3">
        <div className={`num text-[28px] font-semibold leading-none tracking-[-0.035em] ${color}`}>{value}</div>
        {trend && trend.length > 1 && <Spark values={trend} color={hex} className="mb-0.5 h-6 w-16 shrink-0" />}
      </div>
      {sub && <div className="mt-1.5 text-[12px] text-ink-400">{sub}</div>}
    </div>
  );
}

export function Loading({ label = 'Loading…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-2.5 p-4">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton h-3.5 animate-shimmer rounded" style={{ width: `${92 - i * 17}%` }} />
      ))}
    </div>
  );
}

function StateIcon({ children }: { children: ReactNode }) {
  return <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-md border border-line-strong bg-ink-850 text-ink-300">{children}</div>;
}

export function ErrorState({ error, onRetry, compact }: { error: ApiError | Error; onRetry?: () => void; compact?: boolean }) {
  const status = (error as ApiError).status;
  const unreachable = status === 0;
  return (
    <div role="alert" className={`flex flex-col items-start ${compact ? 'p-5' : 'p-8'}`}>
      <StateIcon>
        <AlertTriangle className="h-4 w-4 text-throttle" aria-hidden />
      </StateIcon>
      <p className="text-[14px] font-medium text-ink-50">{unreachable ? 'Gateway unreachable' : 'Something went wrong'}</p>
      <p className="mt-1 max-w-md text-[13px] text-ink-300">{error.message}</p>
      {unreachable && (
        <p className="mt-2 max-w-md text-[12.5px] text-ink-400">
          Check that the Sentinel backend is running and that this dashboard points at it (VITE_API_URL or a dev proxy).
        </p>
      )}
      {onRetry && (
        <button className="btn-secondary mt-4" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start p-8">
      <StateIcon>
        <Inbox className="h-4 w-4" aria-hidden />
      </StateIcon>
      <p className="text-[14px] font-medium text-ink-50">{title}</p>
      {children && <div className="mt-1 max-w-md text-[13px] text-ink-300">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function CodeBlock({ code, className = '', maxHeight = 'max-h-80' }: { code: string; className?: string; maxHeight?: string }) {
  return (
    <pre
      tabIndex={0}
      className={`${maxHeight} overflow-auto rounded-md border border-line bg-ink-950 p-3.5 font-mono text-[12.5px] leading-[1.65] text-ink-100 ${className}`}
    >
      <code>{code}</code>
    </pre>
  );
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line-faint py-2 last:border-0">
      <dt className="text-[13px] text-ink-400">{label}</dt>
      <dd className="num text-right text-[13px] font-medium text-ink-50">{children}</dd>
    </div>
  );
}

/** Fades content up when it scrolls into view; renders immediately for reduced-motion users. */
export function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { threshold: 0.12 },
    );
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      className={`${shown ? 'animate-fade-up' : 'opacity-0'} ${className}`}
      style={shown && delay ? { animationDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}

/** Wraps an async hook state: error → retry panel, first load → skeleton, otherwise children(data). */
export function Async<T>({
  state,
  children,
  loadingRows,
}: {
  state: { data: T | null; error: ApiError | null; loading: boolean; reload: () => void };
  children: (data: T) => ReactNode;
  loadingRows?: number;
}) {
  if (state.data === null) {
    if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
    return <Loading rows={loadingRows} />;
  }
  return <>{children(state.data)}</>;
}
