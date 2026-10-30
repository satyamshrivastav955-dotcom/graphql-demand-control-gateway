import { Link } from 'react-router-dom';
import { api } from '../../api/client';
import type { CSSProperties } from 'react';
import type { Evaluation as Eval } from '../../api/types';
import { useApi } from '../../hooks/useApi';
import { fmtDateTime, fmtFixed, fmtInt, fmtPct } from '../../lib';
import { Async, EmptyState, KV, PageHeader, Panel } from '../../components/ui/primitives';

type Available = Extract<Eval, { available: true }>;

export function EvaluationEmpty() {
  return (
    <EmptyState title="No evaluation results yet">
      The benchmark has not been run, or its results are not available to this gateway. Results appear here only when the evaluation pipeline has produced real artifacts — nothing is estimated or pre-filled. See the project documentation for how to run it.
    </EmptyState>
  );
}

const num = (n: number | null | undefined, d = 3) => (n === null || n === undefined ? '–' : n.toFixed(d));

export function MethodsTable({ e }: { e: Available }) {
  const best = Math.max(...e.methods.map((m) => m.f1));
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Methods table">
      <table className="w-full min-w-[760px]">
        <thead className="border-b border-line">
          <tr>
            <th className="th">Method</th>
            <th className="th text-right">Precision</th>
            <th className="th text-right">Recall</th>
            <th className="th text-right">F1</th>
            <th className="th w-24" aria-hidden />
            <th className="th text-right">FPR</th>
            <th className="th text-right">ROC-AUC</th>
            <th className="th text-right">PR-AUC</th>
            <th className="th text-right">Latency p50 / p95</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line-faint">
          {e.methods.map((m) => (
            <tr key={m.name} className="hover:bg-white/[0.03]">
              <td className="td py-2.5">
                <div className="font-medium text-ink-50">{m.name}</div>
                <div className="mt-0.5 max-w-xs text-[12px] text-ink-400">{m.description}</div>
              </td>
              <td className="td num text-right">{num(m.precision)}</td>
              <td className="td num text-right">{num(m.recall)}</td>
              <td className={`td num text-right font-semibold ${m.f1 === best ? 'text-ink-50' : 'text-ink-200'}`}>{num(m.f1)}</td>
              <td className="td" aria-hidden>
                <div className="h-1 w-20 overflow-hidden rounded-full bg-white/10">
                  <div className={`h-full rounded-full ${m.f1 === best ? 'bg-white' : 'bg-ink-500'}`} style={{ width: `${Math.max(0, Math.min(1, m.f1)) * 100}%` }} />
                </div>
              </td>
              <td className="td num text-right">{num(m.fpr)}</td>
              <td className="td num text-right">{num(m.roc_auc)}</td>
              <td className="td num text-right">{num(m.pr_auc)}</td>
              <td className="td num whitespace-nowrap text-right text-ink-300">
                {fmtFixed(m.latency_us_p50, 0)} / {fmtFixed(m.latency_us_p95, 0)} µs
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function cellStyle(rate: number, attack: boolean): CSSProperties {
  // attacks: high detection is good (green); benign: high "detection" is a false positive (red)
  const good = attack ? rate : 1 - rate;
  const hue = good > 0.5 ? '62,207,142' : '245,89,78';
  const alpha = 0.05 + Math.abs(good - 0.5) * 0.42;
  return { background: `rgba(${hue},${alpha.toFixed(2)})` };
}

export function EvaluationReport({ e }: { e: Available }) {
  const methodNames = e.methods.map((m) => m.name);
  return (
    <div className="space-y-5">
      <div className="grid gap-5 md:grid-cols-3">
        <Panel title="Dataset">
          <dl className="px-4 py-1.5">
            <KV label="Version">{e.dataset.version}</KV>
            <KV label="Train / val / test">
              {fmtInt(e.dataset.n_train)} / {fmtInt(e.dataset.n_val)} / {fmtInt(e.dataset.n_test)}
            </KV>
            <KV label="Attack share (test)">{fmtPct(e.dataset.attack_ratio_test)}</KV>
            <KV label="Categories">{e.dataset.categories.length}</KV>
          </dl>
        </Panel>
        <Panel title="Run">
          <dl className="px-4 py-1.5">
            <KV label="Generated">{fmtDateTime(e.generated_at)}</KV>
            <KV label="Seed">{e.seed}</KV>
            <KV label="Python">{e.environment.python}</KV>
          </dl>
        </Panel>
        <Panel title="Environment">
          <dl className="px-4 py-1.5">
            <KV label="Platform">{e.environment.platform}</KV>
            <KV label="CPU">{e.environment.cpu}</KV>
          </dl>
        </Panel>
      </div>

      <Panel title="Methods compared" hint="Held-out test split. “Detected” means flagged: MEDIUM risk or above, or a hard-limit violation.">
        <MethodsTable e={e} />
      </Panel>

      <Panel title="Confusion matrices" hint="Counts on the held-out test split">
        <div className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-5">
          {e.methods.map((m) => (
            <div key={m.name} className="bg-ink-900 p-3.5">
              <div className="mb-2.5 truncate text-[13px] font-medium text-ink-50" title={m.name}>
                {m.name}
              </div>
              <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md bg-line text-center">
                {[
                  ['true pos', m.confusion.tp, 'text-allow'],
                  ['false pos', m.confusion.fp, 'text-block'],
                  ['false neg', m.confusion.fn, 'text-block'],
                  ['true neg', m.confusion.tn, 'text-allow'],
                ].map(([label, n, tone]) => (
                  <div key={label as string} className="bg-ink-950 px-2 py-2">
                    <div className={`num text-[16px] font-semibold leading-tight ${tone}`}>{fmtInt(n as number)}</div>
                    <div className="text-[11px] text-ink-400">{label as string}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Detection rate by category" hint="Share of each category's samples that was flagged (MEDIUM risk or above, or a hard-limit violation). For benign categories, lower is better.">
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Detection rate by category table">
          <table className="w-full min-w-[560px]">
            <thead className="border-b border-line">
              <tr>
                <th className="th">Category</th>
                <th className="th text-right">n</th>
                {methodNames.map((n) => (
                  <th key={n} className="th text-right">
                    {n}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {e.per_category.map((c) => (
                <tr key={c.category} className="border-b border-line-faint">
                  <td className="td">
                    <span className="capitalize text-ink-50">{c.category.replace(/_/g, ' ')}</span>
                    <span className={`ml-2 text-[11px] ${c.is_attack ? 'text-block' : 'text-allow'}`}>{c.is_attack ? 'attack' : 'benign'}</span>
                  </td>
                  <td className="td text-right tabular-nums text-ink-300">{fmtInt(c.n)}</td>
                  {methodNames.map((n) => {
                    const r = c.detection_rate[n];
                    return (
                      <td key={n} className="td num text-right" style={r === undefined ? undefined : cellStyle(r, c.is_attack)}>
                        {r === undefined ? '–' : fmtPct(r, 1)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-5 md:grid-cols-2">
        {e.real_world_benign && (
          <Panel title="Real-world benign queries" hint={`${e.real_world_benign.source} · n = ${fmtInt(e.real_world_benign.n)}`}>
            <dl className="px-4 py-1.5">
              {Object.entries(e.real_world_benign.false_positive_rate).map(([k, v]) => (
                <KV key={k} label={`${k} false-positive rate`}>
                  {fmtPct(v, 2)}
                </KV>
              ))}
            </dl>
          </Panel>
        )}
        <Panel title="Live gateway overhead" hint="Measured end to end through the running gateway, separate from offline classifier latency">
          {e.gateway_overhead ? (
            <dl className="px-4 py-1.5">
              <KV label="Median">{fmtFixed(e.gateway_overhead.p50_ms, 2)} ms</KV>
              <KV label="95th percentile">{fmtFixed(e.gateway_overhead.p95_ms, 2)} ms</KV>
              <KV label="Throughput">{fmtFixed(e.gateway_overhead.requests_per_second, 0)} req/s</KV>
              <KV label="Requests measured">{fmtInt(e.gateway_overhead.n)}</KV>
            </dl>
          ) : (
            <EmptyState title="Not measured" />
          )}
        </Panel>
      </div>

      <Panel title="Limitations">
        {e.limitations.length ? (
          <ul className="list-disc space-y-1.5 px-8 py-3.5 text-[13px] text-ink-200 marker:text-ink-500">
            {e.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-3.5 text-[13px] text-ink-300">No limitations were recorded with this run.</p>
        )}
      </Panel>
    </div>
  );
}

export default function EvaluationPage() {
  const state = useApi((s) => api.evaluation(s), []);
  return (
    <>
      <PageHeader
        title="Evaluation"
        description="Benchmark results produced by the evaluation pipeline, with the methodology and limitations that go with them."
        actions={
          <Link to="/" className="text-[12.5px] text-ink-300 hover:text-ink-50">
            About the project →
          </Link>
        }
      />
      <Async state={state}>
        {(e) =>
          e.available ? (
            <EvaluationReport e={e} />
          ) : (
            <Panel>
              <EvaluationEmpty />
            </Panel>
          )
        }
      </Async>
    </>
  );
}
