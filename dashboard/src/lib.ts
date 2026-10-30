import type { Decision, Enforced, Severity, Tier } from './api/types';

export const DECISION_STYLE: Record<Decision, { text: string; bg: string; border: string; fill: string; hex: string }> = {
  ALLOW: { text: 'text-allow', bg: 'bg-allow/10', border: 'border-allow/30', fill: 'bg-allow', hex: '#3ecf8e' },
  THROTTLE: { text: 'text-throttle', bg: 'bg-throttle/10', border: 'border-throttle/30', fill: 'bg-throttle', hex: '#f5a524' },
  BLOCK: { text: 'text-block', bg: 'bg-block/10', border: 'border-block/30', fill: 'bg-block', hex: '#f5594e' },
  ERROR: { text: 'text-fault', bg: 'bg-fault/10', border: 'border-fault/30', fill: 'bg-fault', hex: '#a4a7ae' },
};

export const TIER_STYLE: Record<Tier, { text: string; fill: string; hex: string; label: string }> = {
  SAFE: { text: 'text-allow', fill: 'bg-allow', hex: '#3ecf8e', label: 'Safe' },
  LOW_RISK: { text: 'text-low', fill: 'bg-low', hex: '#a4d65e', label: 'Low risk' },
  MEDIUM_RISK: { text: 'text-throttle', fill: 'bg-throttle', hex: '#f5a524', label: 'Medium risk' },
  HIGH_RISK: { text: 'text-high', fill: 'bg-high', hex: '#f08a3b', label: 'High risk' },
  CRITICAL: { text: 'text-block', fill: 'bg-block', hex: '#f5594e', label: 'Critical' },
};

export const SEVERITY_STYLE: Record<Severity, string> = {
  info: 'bg-ink-400',
  low: 'bg-low',
  medium: 'bg-throttle',
  high: 'bg-block',
};

/** True when an event/response was recorded in shadow (report-only) mode, i.e. not enforced. */
export const isShadow = (enforced?: Enforced | null, flag?: boolean) => flag === true || enforced === 'shadow';

/** Wording for a decision: in shadow mode a block/throttle is what the gateway *would* have done. */
export function decisionLabel(decision: Decision, shadow = false): string {
  if (!shadow) return decision;
  return decision === 'BLOCK' ? 'WOULD BLOCK' : decision === 'THROTTLE' ? 'WOULD THROTTLE' : decision;
}

export const fmtInt = (n: number | undefined | null) =>
  n === undefined || n === null ? '–' : new Intl.NumberFormat('en-US').format(n);

export const fmtFixed = (n: number | undefined | null, d = 1) =>
  n === undefined || n === null || Number.isNaN(n) ? '–' : n.toFixed(d);

export const fmtPct = (ratio: number | undefined | null, d = 1) =>
  ratio === undefined || ratio === null || Number.isNaN(ratio) ? '–' : `${(ratio * 100).toFixed(d)}%`;

export const fmtMs = (ms: number | undefined | null) =>
  ms === undefined || ms === null ? '–' : ms < 1 ? `${ms.toFixed(2)} ms` : `${ms.toFixed(1)} ms`;

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function fmtBytes(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MiB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${n} B`;
}

export const snippet = (q: string, max = 70) => {
  const flat = q.replace(/\s+/g, ' ').trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
};

const ACRONYMS: Record<string, string> = { ml: 'ML', ai: 'AI', ip: 'IP' };
export const humanize = (s: string) =>
  s.replace(/_/g, ' ').replace(/\b(ml|ai|ip)\b/gi, (m) => ACRONYMS[m.toLowerCase()]);

/** A copyable curl for sending one operation through the gateway (shell-quoted; the key is read from the environment). */
export function curlFor(query: string, opts: { origin?: string; withKey?: boolean } = {}): string {
  const body = JSON.stringify({ query }).replace(/'/g, "'\\''");
  const lines = [`curl -s ${opts.origin ?? ''}/graphql-proxy`, "  -H 'content-type: application/json'"];
  if (opts.withKey) lines.push('  -H "X-API-Key: $SENTINEL_API_KEY"');
  lines.push(`  -d '${body}'`);
  return lines.join(' \\\n');
}
