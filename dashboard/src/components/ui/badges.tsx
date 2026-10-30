import type { Decision, Severity, Tier } from '../../api/types';
import { DECISION_STYLE, SEVERITY_STYLE, TIER_STYLE, decisionLabel } from '../../lib';

/**
 * A decision is a status dot plus its name in the decision colour, not a filled pill. In shadow mode a block or
 * throttle is hollow and reads "would block": recorded, not enforced.
 */
export function DecisionBadge({ decision, size = 'md', shadow = false }: { decision: Decision; size?: 'sm' | 'md' | 'lg'; shadow?: boolean }) {
  const s = DECISION_STYLE[decision] ?? DECISION_STYLE.ERROR;
  const hollow = shadow && (decision === 'BLOCK' || decision === 'THROTTLE');
  const text = size === 'lg' ? 'text-[15px]' : size === 'sm' ? 'text-[11px]' : 'text-[12px]';
  const dot = size === 'lg' ? 'h-2.5 w-2.5' : 'h-1.5 w-1.5';
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-semibold tracking-[0.01em] ${text} ${s.text}`}
      title={hollow ? 'Shadow mode: recorded, not enforced' : undefined}
    >
      <span
        className={`${dot} shrink-0 rounded-full ${hollow ? 'border-[1.5px] bg-transparent' : s.fill}`}
        style={hollow ? { borderColor: s.hex } : undefined}
        aria-hidden
      />
      {decisionLabel(decision, hollow)}
    </span>
  );
}

export function TierBadge({ tier }: { tier: Tier }) {
  const s = TIER_STYLE[tier];
  if (!s) return <span className="text-ink-300">{tier}</span>;
  return <span className={`whitespace-nowrap text-[12px] font-medium ${s.text}`}>{s.label}</span>;
}

export function SeverityDot({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${SEVERITY_STYLE[severity] ?? 'bg-ink-400'}`}
      title={`${severity} severity`}
    />
  );
}

/** Horizontal 0-100 meter; ticks mark the tier boundaries so the number has a scale. */
export function ScoreBar({ score, tier, className = '' }: { score: number; tier?: Tier; className?: string }) {
  const pct = Math.max(0, Math.min(100, score));
  const color = tier ? TIER_STYLE[tier].fill : pct > 85 ? 'bg-block' : pct > 65 ? 'bg-high' : pct > 40 ? 'bg-throttle' : 'bg-allow';
  return (
    <div
      className={`relative h-1 w-full overflow-hidden rounded-full bg-white/10 ${className}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-label="Risk score"
    >
      <div className={`h-full rounded-full transition-[width] duration-500 ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}
