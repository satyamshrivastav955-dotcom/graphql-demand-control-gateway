import { AlertTriangle } from 'lucide-react';
import TierScale from '../../components/TierScale';
import { api } from '../../api/client';
import { TIERS, Tier } from '../../api/types';
import { useApi } from '../../hooks/useApi';
import { DECISION_STYLE, TIER_STYLE, fmtBytes, fmtDateTime, fmtInt } from '../../lib';
import { DecisionBadge } from '../../components/ui/badges';
import { Async, KV, PageHeader, Panel } from '../../components/ui/primitives';
import { ShadowBanner } from '../../components/ui/ShadowBanner';

const INTROSPECTION_TEXT = {
  allow: 'Allowed — introspection queries are scored like any other operation.',
  flag: 'Flagged — introspection raises the risk score but is not rejected outright.',
  block: 'Blocked — introspection operations are rejected.',
} as const;

export default function Policies() {
  const state = useApi((s) => api.config(s), []);
  return (
    <>
      <PageHeader
        title="Policies"
        description="The configuration the gateway is currently enforcing. This view is read-only; change settings through environment variables or the settings file and restart."
      />
      <Async state={state}>
        {(c) => {
          const bounds: Record<Tier, [number, number]> = {
            SAFE: [0, c.tiers.safe],
            LOW_RISK: [c.tiers.safe, c.tiers.low_risk],
            MEDIUM_RISK: [c.tiers.low_risk, c.tiers.medium_risk],
            HIGH_RISK: [c.tiers.medium_risk, c.tiers.high_risk],
            CRITICAL: [c.tiers.high_risk, 100],
          };
          return (
            <div className="space-y-5">
              {c.enforcement === 'shadow' && <ShadowBanner className="rounded-lg border" />}
              {c.mode === 'simulation' && (
                <div role="alert" className="flex items-start gap-3 rounded-lg border border-throttle/30 bg-throttle/[0.08] p-3.5 text-[13px] text-throttle">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  <div>
                    <p className="font-medium">Simulation mode</p>
                    <p className="mt-0.5 text-throttle/90">No upstream is configured. Decisions are made normally, but allowed requests return a labelled simulated response instead of real data.</p>
                  </div>
                </div>
              )}

              <Panel title="Risk tiers and actions" hint="The final 0–100 score maps to a tier, and each tier to an enforced action">
                <div className="border-b border-line px-4 py-4">
                  <TierScale bounds={[c.tiers.safe, c.tiers.low_risk, c.tiers.medium_risk, c.tiers.high_risk]} />
                </div>
                <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Risk tiers table">
                  <table className="w-full min-w-[480px]">
                    <thead className="border-b border-line">
                      <tr>
                        <th className="th">Tier</th>
                        <th className="th">Score range</th>
                        <th className="th">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line-faint">
                      {TIERS.map((t) => (
                        <tr key={t}>
                          <td className={`td font-medium ${TIER_STYLE[t].text}`}>{TIER_STYLE[t].label}</td>
                          <td className="td num text-ink-200">
                            {t === 'SAFE' ? '0' : `> ${bounds[t][0]}`} – {bounds[t][1]}
                          </td>
                          <td className="td">
                            <DecisionBadge decision={c.tier_actions[t]} size="sm" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="border-t border-line px-4 py-2.5 text-[12px] text-ink-400">
                  Only operations that end in{' '}
                  <span className={DECISION_STYLE.ALLOW.text}>ALLOW</span> or an allowed <span className={DECISION_STYLE.THROTTLE.text}>THROTTLE</span> (within the rate limit) are forwarded.
                </p>
              </Panel>

              <div className="grid gap-5 md:grid-cols-2">
                <Panel title="Hard limits" hint="Limits checked while analysing each operation">
                  <dl className="px-4 py-1.5">
                    <KV label="Max request body">{fmtBytes(c.limits.max_body_bytes)}</KV>
                    <KV label="Max query length">{fmtInt(c.limits.max_query_length)} chars</KV>
                    <KV label="Max depth">{c.limits.max_depth}</KV>
                    <KV label="Max aliases">{c.limits.max_aliases}</KV>
                    <KV label="Max complexity">{fmtInt(c.limits.max_complexity)}</KV>
                    <KV label="Max tokens">{fmtInt(c.limits.max_tokens)}</KV>
                  </dl>
                </Panel>
                <div className="space-y-5">
                  <Panel title="Throttling">
                    <dl className="px-4 py-1.5">
                      <KV label="Rate limit">
                        {c.throttle.rate_limit} req / {c.throttle.window_seconds}s
                      </KV>
                    </dl>
                    <p className="border-t border-line px-4 py-2.5 text-[12px] text-ink-400">Requests above the limit receive HTTP 429 with a Retry-After header.</p>
                  </Panel>
                  <Panel title="Introspection">
                    <div className="px-4 py-3.5">
                      <p className="text-[13px] font-medium capitalize text-ink-50">{c.introspection}</p>
                      <p className="mt-1 text-[13px] text-ink-300">{INTROSPECTION_TEXT[c.introspection]}</p>
                    </div>
                  </Panel>
                </div>
              </div>

              <div className="grid gap-5 md:grid-cols-2">
                <Panel title="Upstream">
                  <dl className="px-4 py-1.5">
                    <KV label="Mode">{c.mode}</KV>
                    <KV label="Enforcement">{c.enforcement === 'shadow' ? 'Shadow: record only, never block' : c.enforcement === 'enforce' ? 'Enforce' : '–'}</KV>
                    <KV label="Configured">{c.upstream_configured ? 'Yes' : 'No'}</KV>
                    <KV label="Host">{c.upstream_host ?? '–'}</KV>
                  </dl>
                </Panel>
                <Panel title="ML model">
                  <dl className="px-4 py-1.5">
                    <KV label="Loaded">{c.model.loaded ? 'Yes' : 'No'}</KV>
                    <KV label="Name">{c.model.name ?? '–'}</KV>
                    <KV label="Trained">{c.model.trained_at ? fmtDateTime(c.model.trained_at) : '–'}</KV>
                    <KV label="Features">{c.model.n_features ?? '–'}</KV>
                  </dl>
                </Panel>
              </div>
              <p className="text-[12px] text-ink-400">Gateway version {c.version}</p>
            </div>
          );
        }}
      </Async>
    </>
  );
}
