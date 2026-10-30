import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useApi } from '../hooks/useApi';

/** The mark: three requests approach a gate; one passes. */
export function Logo({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="7" fill="#fff" />
      <path d="M6.5 10.5h9M6.5 16h9M6.5 21.5h9" stroke="#08090a" strokeWidth="2.4" strokeLinecap="round" />
      <rect x="18.5" y="6.5" width="3.2" height="19" rx="1.6" fill="#08090a" />
      <path d="M23.5 16h2.5" stroke="#08090a" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ to = '/', label = 'Sentinel' }: { to?: string; label?: string }) {
  return (
    <Link to={to} aria-label="Sentinel home" className="flex items-center gap-2 whitespace-nowrap text-ink-50">
      <Logo />
      <span className="text-[15px] font-semibold tracking-[-0.02em]">{label}</span>
    </Link>
  );
}

/** Truthful gateway health indicator driven by /api/ready. */
export function GatewayStatus({ compact = false, collapseOnMobile = false }: { compact?: boolean; collapseOnMobile?: boolean }) {
  const { data, error, loading } = useApi((s) => api.ready(s), [], 15000);

  let label = 'Checking gateway…';
  let dot = 'bg-ink-400';
  let ping = false;
  if (!loading || data || error) {
    if (data && data.status === 'ready') {
      label = data.checks?.upstream === 'simulation' ? 'Online · simulation mode' : 'Gateway online';
      dot = data.checks?.upstream === 'simulation' ? 'bg-throttle' : 'bg-allow';
      ping = true;
    } else if (data) {
      const up = data.checks?.upstream;
      label = up === 'unreachable' ? 'Degraded · upstream unreachable' : up === 'not_configured' ? 'Degraded · no upstream' : 'Degraded';
      dot = 'bg-throttle';
    } else {
      label = 'Gateway offline';
      dot = 'bg-block';
    }
  }
  return (
    <div role="status" className="inline-flex items-center gap-2 text-[12.5px] text-ink-300" title="Reported by GET /api/ready">
      <span className="relative flex h-1.5 w-1.5">
        {ping && <span className={`absolute inline-flex h-full w-full animate-live-ping rounded-full ${dot}`} />}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${dot}`} />
      </span>
      {compact ? (
        <span className="sr-only">{label}</span>
      ) : collapseOnMobile ? (
        <span className="sr-only sm:not-sr-only sm:whitespace-nowrap">{label}</span>
      ) : (
        <span>{label}</span>
      )}
    </div>
  );
}
