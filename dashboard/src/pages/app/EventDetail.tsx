import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { api, API_BASE } from '../../api/client';
import { useApi } from '../../hooks/useApi';
import { curlFor, fmtDateTime, fmtFixed, fmtMs, humanize, isShadow } from '../../lib';
import { DecisionBadge, TierBadge } from '../../components/ui/badges';
import { Async, EmptyState, ErrorState, KV, Panel } from '../../components/ui/primitives';
import { Sparkline } from '../../components/charts';
import { CopyButtonInline } from '../../components/CopyButtonInline';
import { QueryView, lineMarks } from '../../components/code';
import RuleWaterfall from '../../components/RuleWaterfall';
import TierScale from '../../components/TierScale';

export default function EventDetail() {
  const { id = '' } = useParams();
  const state = useApi((s) => api.event(id, s), [id]);

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-2 text-[13px] text-ink-400">
        <Link to="/app/events" className="inline-flex items-center gap-1.5 hover:text-ink-50">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> All events
        </Link>
        <span aria-hidden>/</span>
        <span className="num truncate font-mono text-[12px]">{id}</span>
      </nav>
      <h1 className="sr-only">Security event</h1>
      {state.error?.status === 404 ? (
        <Panel>
          <EmptyState title="Event not found" action={<Link to="/app/events" className="btn-secondary">Back to events</Link>}>
            It may have expired from the event store, or the link is wrong.
          </EmptyState>
        </Panel>
      ) : state.error && !state.data ? (
        <Panel>
          <ErrorState error={state.error} onRetry={state.reload} />
        </Panel>
      ) : (
        <Async state={state}>
          {(e) => {
            const marks = lineMarks(e.query, e.explanations.map((x) => x.rule));
            return (
              <div className="space-y-5">
                <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line pb-4">
                  <DecisionBadge decision={e.decision} size="lg" shadow={isShadow(e.enforced)} />
                  {e.risk_tier && <TierBadge tier={e.risk_tier} />}
                  <span className="num text-[13px] text-ink-300">{fmtDateTime(e.timestamp)}</span>
                  <span className="ml-auto">
                    <CopyButtonInline text={curlFor(e.query, { origin: API_BASE || window.location.origin, withKey: true })} label="Copy as curl" />
                  </span>
                </header>

                <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
                  <div className="min-w-0 space-y-5">
                    <Panel title="Operation" hint={marks.size ? 'Highlighted lines triggered rules' : undefined}>
                      <div className="p-3">
                        <QueryView code={e.query} marks={marks} />
                      </div>
                    </Panel>

                    <Panel title="Why this decision">
                      {e.explanations.length ? (
                        <RuleWaterfall explanations={e.explanations} ruleScore={e.rule_score} mlScore={e.ml_score} score={e.score} />
                      ) : e.score == null ? (
                        <EmptyState title="Not analysed">Rejected by the rate limiter before the operation was scored.</EmptyState>
                      ) : (
                        <EmptyState title="No rules fired" />
                      )}
                      {e.limit_violations.length > 0 && (
                        <div className="border-t border-line px-4 py-3">
                          <div className="panel-title mb-1.5">Limit violations</div>
                          <ul className="space-y-1 font-mono text-[12.5px] text-block">
                            {e.limit_violations.map((v) => (
                              <li key={v}>{v}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </Panel>

                    <Panel title="Extracted features">
                      <dl className="grid grid-cols-2 gap-x-5 px-4 py-1.5 sm:grid-cols-3">
                        {Object.entries(e.features).map(([k, v]) => (
                          <div key={k} className="flex items-baseline justify-between gap-2 border-b border-line-faint py-1.5">
                            <dt className="truncate font-mono text-[11.5px] text-ink-400" title={k}>
                              {k}
                            </dt>
                            <dd className="num text-[13px] font-medium text-ink-50">{Number.isInteger(v) ? v : fmtFixed(v, 3)}</dd>
                          </div>
                        ))}
                      </dl>
                    </Panel>
                  </div>

                  <aside aria-label="Event context" className="min-w-0 space-y-5 lg:sticky lg:top-[68px]">
                    <Panel title="Score">
                      <div className="p-4">
                        <div className="flex items-baseline justify-between">
                          <span className="text-[13px] text-ink-300">Final score</span>
                          <span className="num text-[30px] font-semibold leading-none tracking-[-0.04em] text-ink-50">{fmtFixed(e.score, 1)}</span>
                        </div>
                        <div className="mt-3">
                          <TierScale score={e.score} />
                        </div>
                        <dl className="mt-3">
                          <KV label="Rule score">{fmtFixed(e.rule_score, 1)}</KV>
                          <KV label="ML score">{e.ml_score === null ? 'n/a' : fmtFixed(e.ml_score, 3)}</KV>
                        </dl>
                      </div>
                    </Panel>
                    <Panel title="Enforcement">
                      <dl className="px-4 py-1.5">
                        <KV label="Outcome">{isShadow(e.enforced) ? 'Shadow: recorded, not enforced' : humanize(e.enforced)}</KV>
                        <KV label="Upstream status">{e.upstream_status ?? '–'}</KV>
                        <KV label="Analysis time">{fmtMs(e.latency_ms)}</KV>
                        <KV label="Total time">{fmtMs(e.total_latency_ms)}</KV>
                      </dl>
                    </Panel>
                    <Panel title="Request">
                      <dl className="px-4 py-1.5">
                        <KV label="Type">{e.operation_type ?? '–'}</KV>
                        <KV label="Operation">{e.operation_name ?? '–'}</KV>
                        <KV label="Client">{e.client_id}</KV>
                        <KV label="IP">{e.ip}</KV>
                      </dl>
                    </Panel>
                    <Panel title="Client history" hint="Risk score of this client's recent requests">
                      <div className="p-4">
                        <Sparkline points={e.client_timeline} />
                      </div>
                    </Panel>
                  </aside>
                </div>
              </div>
            );
          }}
        </Async>
      )}
    </>
  );
}
