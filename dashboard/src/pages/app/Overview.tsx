import { useState } from 'react';
import { Link } from 'react-router-dom';
import FirstRun from '../../components/FirstRun';
import { RefreshCw } from 'lucide-react';
import { api } from '../../api/client';
import { useEnforcement } from '../../hooks/enforcement';
import { DECISIONS, TIERS } from '../../api/types';
import { useApi } from '../../hooks/useApi';
import { fmtInt, fmtMs, fmtPct, fmtFixed, DECISION_STYLE, TIER_STYLE, humanize } from '../../lib';
import { Async, EmptyState, PageHeader, Panel, Stat, StatStrip } from '../../components/ui/primitives';
import { LoadChart, SegmentBar } from '../../components/charts';
import EventsTable from '../../components/EventsTable';

const RANGES = [
  { minutes: 15, label: 'Last 15 min' },
  { minutes: 60, label: 'Last hour' },
  { minutes: 360, label: 'Last 6 hours' },
  { minutes: 1440, label: 'Last 24 hours' },
];

export default function Overview() {
  const [minutes, setMinutes] = useState(60);
  const state = useApi((s) => api.metrics(minutes, s), [minutes], 10000);
  const shadow = useEnforcement() === 'shadow';

  return (
    <>
      <PageHeader
        title="Overview"
        description={shadow ? 'What the gateway has analysed. It is in shadow mode, so nothing was blocked or throttled. Every figure is computed by the backend from stored security events.' : 'What the gateway has analysed and enforced. Every figure is computed by the backend from stored security events.'}
        actions={
          <>
            {state.refreshing && <RefreshCw className="h-3.5 w-3.5 animate-spin text-ink-400" aria-label="Refreshing" />}
            <label className="sr-only" htmlFor="range">
              Time range
            </label>
            <select id="range" className="field w-auto pr-7" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
              {RANGES.map((r) => (
                <option key={r.minutes} value={r.minutes}>
                  {r.label}
                </option>
              ))}
            </select>
          </>
        }
      />

      <Async state={state}>
        {(m) => {
          const series = (k: 'total' | 'allowed' | 'throttled' | 'blocked') => m.load_over_time.map((p) => p[k]);
          const maxSignal = Math.max(1, ...m.top_signals.map((s) => s.count));
          return m.total_queries === 0 ? (
            <Panel>
              <FirstRun title="No traffic in this window" onSent={state.reload} />
            </Panel>
          ) : (
            <div className="space-y-5">
              <StatStrip>
                <Stat label="Requests" value={fmtInt(m.total_queries)} sub={`${fmtInt(m.active_clients)} active clients`} source="Count of events in the selected window" trend={series('total')} />
                <Stat label="Allowed" value={fmtInt(m.allowed_count)} tone="allow" sub={fmtPct(m.allowed_count / m.total_queries) + ' of traffic'} trend={series('allowed')} />
                <Stat label={shadow ? 'Would throttle' : 'Throttled'} value={fmtInt(m.throttled_count)} tone="throttle" sub={fmtPct(m.throttled_count / m.total_queries) + ' of traffic'} trend={series('throttled')} />
                <Stat label={shadow ? 'Would block' : 'Blocked'} value={fmtInt(m.blocked_count)} tone="block" sub={`${shadow ? 'would-block' : 'block'} rate ${fmtPct(m.block_rate)}`} trend={series('blocked')} />
              </StatStrip>
              <StatStrip>
                <Stat label="Avg risk score" value={fmtFixed(m.avg_score, 1)} sub="0 – 100, higher is riskier" />
                <Stat label="Avg analysis time" value={fmtMs(m.avg_latency_ms)} sub="parse + score, excludes upstream" source="Measured per request by the gateway" />
                <Stat label="p95 analysis time" value={fmtMs(m.p95_latency_ms)} sub="95th percentile" />
                <Stat label="Errors" value={fmtInt(m.error_count)} sub="malformed or rejected input" />
              </StatStrip>

              <div className="grid gap-5 lg:grid-cols-3">
                <Panel title="Request volume" hint="Per-minute counts by enforcement outcome" className="lg:col-span-2">
                  {m.load_over_time.length ? <LoadChart points={m.load_over_time} /> : <EmptyState title="No timeline data" />}
                </Panel>
                <Panel title="Decisions">
                  <SegmentBar
                    segments={DECISIONS.map((d) => ({
                      key: d,
                      label: d[0] + d.slice(1).toLowerCase(),
                      value: m.decision_distribution[d] ?? 0,
                      color: DECISION_STYLE[d].hex,
                    }))}
                  />
                </Panel>
              </div>

              <div className="grid gap-5 md:grid-cols-2">
                <Panel title="Risk tiers">
                  <SegmentBar
                    segments={TIERS.map((t) => ({
                      key: t,
                      label: TIER_STYLE[t].label,
                      value: m.tier_distribution[t] ?? 0,
                      color: TIER_STYLE[t].hex,
                    }))}
                  />
                </Panel>
                <Panel title="Top signals" hint="Rules that contributed most often">
                  {m.top_signals.length ? (
                    <ul className="px-4 py-2">
                      {m.top_signals.map((s) => (
                        <li key={s.rule} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 py-1.5 text-[13px]">
                          <span className="truncate capitalize text-ink-100">{humanize(s.rule)}</span>
                          <span className="h-1 overflow-hidden rounded-full bg-white/10" aria-hidden>
                            <span className="block h-full rounded-full bg-ink-200" style={{ width: `${(s.count / maxSignal) * 100}%` }} />
                          </span>
                          <span className="num w-10 text-right text-ink-300">{fmtInt(s.count)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState title="No rules fired" />
                  )}
                </Panel>
              </div>

              <Panel
                title="Recent suspicious activity"
                hint="Highest-risk recent events · click a row for the full analysis"
                actions={
                  <Link to="/app/events" className="text-[12.5px] text-ink-300 hover:text-ink-50">
                    All events →
                  </Link>
                }
              >
                {m.recent_suspicious.length ? <EventsTable events={m.recent_suspicious} /> : <EmptyState title="Nothing suspicious in this window" />}
              </Panel>
            </div>
          );
        }}
      </Async>
    </>
  );
}
