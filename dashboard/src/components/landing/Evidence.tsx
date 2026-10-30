import { ReactNode } from 'react';
import type { EvalMethod, Evaluation } from '../../api/types';
import type { ApiState } from '../../hooks/useApi';
import { useInView } from '../../hooks/motion';
import { fmtInt } from '../../lib';

type Available = Extract<Evaluation, { available: true }>;

const SHORT: Record<string, string> = {
  'Hard limits only': 'Hard limits only',
  'Depth/cost threshold': 'One tuned threshold',
  'Rule scorer': 'Rules',
  'ML classifier': 'Model alone',
  'Combined (production)': 'Rules + model',
};
const pct = (v: number) => `${Math.round(v * 100)}%`;
const human = (s: string) => s.replace(/_/g, ' ');

function Pending({ state, what }: { state: ApiState<Evaluation>; what: string }) {
  const error = state.error && state.data === null;
  const box = 'rounded-lg border border-dashed border-line-strong p-6 text-[13.5px] leading-relaxed text-ink-300';
  if (state.data && state.data.available) {
    return (
      <div className={box}>
        <p className="font-medium text-ink-50">This benchmark run has no leave-one-category-out results</p>
        <p className="mt-1">
          Re-run <code className="rounded bg-white/[0.07] px-1.5 py-0.5 font-mono text-[12px] text-ink-100">python -m ml.run</code> to generate them.
        </p>
      </div>
    );
  }
  return (
    <div className={box}>
      {state.loading && !error ? (
        <p role="status">Loading the benchmark…</p>
      ) : error ? (
        <>
          <p className="font-medium text-ink-50">Benchmark unavailable</p>
          <p className="mt-1">The evaluation could not be loaded from the gateway ({state.error?.message}). It is never replaced with placeholder numbers.</p>
        </>
      ) : (
        <>
          <p className="font-medium text-ink-50">No benchmark has been generated yet</p>
          <p className="mt-1">
            {what} is drawn live from <code className="font-mono text-[12px] text-ink-100">/api/evaluation</code>. Generate it with{' '}
            <code className="rounded bg-white/[0.07] px-1.5 py-0.5 font-mono text-[12px] text-ink-100">python -m ml.run</code>.
          </p>
        </>
      )}
    </div>
  );
}

function Caption({ children }: { children: ReactNode }) {
  return <figcaption className="mt-4 text-[12.5px] leading-relaxed text-ink-400">{children}</figcaption>;
}

function MethodRow({ m, seen, i, strong }: { m: EvalMethod; seen: boolean; i: number; strong: boolean }) {
  return (
    <li className="grid grid-cols-[minmax(0,7.5rem)_1fr] items-center gap-x-4 gap-y-1.5 py-3 sm:grid-cols-[9.5rem_1fr_5.5rem]">
      <span className={`text-[13.5px] ${strong ? 'font-semibold text-ink-50' : 'text-ink-300'}`}>{SHORT[m.name] ?? m.name}</span>
      <div className="space-y-1.5" aria-hidden>
        <div className="h-2.5 overflow-hidden rounded-[2px] bg-white/[0.07]">
          <div
            className={`h-full rounded-[2px] transition-[width] duration-1000 ease-out ${strong ? 'bg-white' : 'bg-ink-500'}`}
            style={{ width: seen ? `${m.f1 * 100}%` : '0%', transitionDelay: `${i * 90}ms` }}
          />
        </div>
        <div className="h-[3px] overflow-hidden rounded-full bg-white/[0.07]">
          <div className="h-full rounded-full bg-block transition-[width] duration-1000 ease-out" style={{ width: seen ? `${m.fpr * 100}%` : '0%', transitionDelay: `${i * 90 + 200}ms` }} />
        </div>
      </div>
      <dl className="num col-span-2 flex gap-4 text-[12.5px] sm:col-span-1 sm:block sm:text-right">
        <div>
          <dt className="sr-only">F1</dt>
          <dd className={`text-[13.5px] font-semibold ${strong ? 'text-ink-50' : 'text-ink-200'}`}>F1 {m.f1.toFixed(2)}</dd>
        </div>
        <div>
          <dt className="sr-only">False-positive rate</dt>
          <dd className="text-block">FPR {pct(m.fpr)}</dd>
        </div>
      </dl>
    </li>
  );
}

function Proof({ k, v, note }: { k: string; v: string; note: string }) {
  return (
    <div className="px-5 py-5 sm:py-6">
      <dt className="text-[12.5px] text-ink-400">{k}</dt>
      <dd className="num mt-2 text-[40px] font-semibold leading-none tracking-[-0.045em] text-ink-50">{v}</dd>
      <dd className="mt-2 text-[12.5px] leading-snug text-ink-400">{note}</dd>
    </div>
  );
}

export function EvidenceSection({ state }: { state: ApiState<Evaluation> }) {
  const [ref, seen] = useInView<HTMLElement>(0.2);
  const d = state.data && state.data.available ? (state.data as Available) : null;
  const by = (name: string) => d?.methods.find((m) => m.name === name);
  const limits = by('Hard limits only');
  const tuned = by('Depth/cost threshold');
  const combined = by('Combined (production)');
  const real = d?.real_world_benign?.false_positive_rate?.['Combined (production)'];

  return (
    <section id="evidence" aria-labelledby="evidence-h" className="scroll-mt-20 border-t border-line">
      <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
          <div>
            <h2 id="evidence-h" className="h-section max-w-[16ch]">
              What a single limit cannot see.
            </h2>
            <div className="mt-6 space-y-4 text-[15.5px] leading-relaxed text-ink-300">
              <p>Every GraphQL gateway ships limits for depth, size and cost. They are the right first control. They are also blunt: one threshold has to separate a dashboard with fourteen widgets from an alias-batching attack.</p>
              {limits && tuned && combined ? (
                <p>
                  On the held-out benchmark, hard limits alone reach <strong className="font-semibold text-ink-50">F1 {limits.f1.toFixed(2)}</strong>: they catch {pct(limits.recall)} of abusive operations. Tuning one depth-and-cost
                  threshold catches {pct(tuned.recall)} but flags {pct(tuned.fpr)} of ordinary traffic. Reading the whole operation and combining rules with a model reaches{' '}
                  <strong className="font-semibold text-ink-50">F1 {combined.f1.toFixed(2)}</strong>.
                </p>
              ) : null}
              {d && (
                <p className="text-[13px] text-ink-400">
                  {fmtInt(d.dataset.n_test)} held-out operations, {pct(d.dataset.attack_ratio_test)} abusive. Synthetic data from one fictional schema: it shows the shape of the trade-off, not your production accuracy.
                </p>
              )}
            </div>
          </div>

          <figure ref={ref} aria-label="Detection quality by method" className="min-w-0">
            {d ? (
              <>
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line pb-2.5 text-[12px] text-ink-400">
                  <span className="flex items-center gap-2">
                    <i className="inline-block h-2 w-4 rounded-[2px] bg-white" /> F1 (higher is better)
                  </span>
                  <span className="flex items-center gap-2">
                    <i className="inline-block h-[3px] w-4 rounded-full bg-block" /> False-positive rate
                  </span>
                </div>
                <ul className="divide-y divide-line-faint">
                  {d.methods.map((m, i) => (
                    <MethodRow key={m.name} m={m} seen={seen} i={i} strong={m.name === 'Combined (production)'} />
                  ))}
                </ul>
                <Caption>
                  Held-out test split, seed {d.seed}, dataset v{d.dataset.version}. Flagged means medium risk or above, or a hard-limit violation. Full tables, methodology and limitations are in the repository.
                </Caption>
              </>
            ) : (
              <Pending state={state} what="This chart" />
            )}
          </figure>
        </div>

        {d && limits && combined && (
          <dl className="mt-14 grid grid-cols-2 divide-x divide-line overflow-hidden rounded-lg border border-line lg:grid-cols-4 [&>div:nth-child(n+3)]:border-t [&>div:nth-child(n+3)]:border-line lg:[&>div:nth-child(n+3)]:border-t-0">
            <Proof k="F1 with hard limits only" v={limits.f1.toFixed(2)} note={`${pct(limits.recall)} of abusive operations caught`} />
            <Proof k="F1 reading the whole operation" v={combined.f1.toFixed(2)} note={`${pct(combined.recall)} caught, rules plus model`} />
            <Proof
              k="False positives on real queries"
              v={real !== undefined ? pct(real) : '–'}
              note={d.real_world_benign ? `${d.real_world_benign.n} real benign GraphQL queries` : 'real-query check not in this run'}
            />
            <Proof k="Held-out operations" v={fmtInt(d.dataset.n_test)} note={`${pct(d.dataset.attack_ratio_test)} abusive, seed ${d.seed}`} />
          </dl>
        )}
      </div>
    </section>
  );
}

function Dumbbell({ row, seen, i }: { row: { name: string; ml: number; rules: number; combined: number }; seen: boolean; i: number }) {
  const lo = Math.min(row.ml, row.rules, row.combined);
  const hi = Math.max(row.ml, row.rules, row.combined);
  const at = (v: number) => (seen ? `${v * 100}%` : '0%');
  const delay = `${i * 60}ms`;
  const mk = 'absolute top-1/2 -translate-x-1/2 -translate-y-1/2 transition-[left] duration-1000 ease-out';
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
        <span className="text-[13.5px] capitalize text-ink-100">{human(row.name)}</span>
        <span className="num text-[12px] text-ink-400">
          model {pct(row.ml)} · rules {pct(row.rules)} · both {pct(row.combined)}
        </span>
      </div>
      <div className="relative mt-2 h-4" aria-hidden>
        <div className="absolute inset-x-0 top-1/2 h-px bg-white/[0.12]" />
        <div className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-white/[0.22] transition-all duration-1000" style={{ left: `${seen ? lo * 100 : 0}%`, width: `${seen ? (hi - lo) * 100 : 0}%`, transitionDelay: delay }} />
        <span className={`${mk} h-3 w-3 rounded-full border-2 border-block bg-ink-950`} style={{ left: at(row.ml), transitionDelay: delay }} />
        <span className={`${mk} h-2.5 w-2.5 rotate-45 bg-throttle`} style={{ left: at(row.rules), transitionDelay: delay }} />
        <span className={`${mk} h-3 w-3 rounded-full bg-white`} style={{ left: at(row.combined), transitionDelay: delay }} />
      </div>
    </li>
  );
}

export function GeneralisationSection({ state }: { state: ApiState<Evaluation> }) {
  const [ref, seen] = useInView<HTMLElement>(0.15);
  const d = state.data && state.data.available ? (state.data as Available) : null;
  const folds = d?.generalization?.folds ?? [];
  const rows = [...folds]
    .sort((a, b) => a.ml_recall - b.ml_recall)
    .map((f) => ({ name: f.held_out_category, ml: f.ml_recall, rules: f.rules_recall, combined: f.combined_recall }));
  const mlMethod = d?.methods.find((m) => m.name === 'ML classifier');
  const failing = rows.filter((r) => r.ml < 0.5).length;

  return (
    <section id="model" aria-labelledby="gen-h" className="scroll-mt-20 border-t border-line bg-ink-900/40">
      <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
          <div>
            <h2 id="gen-h" className="h-section max-w-[16ch]">
              Why the model never decides alone.
            </h2>
            <div className="mt-6 space-y-4 text-[15.5px] leading-relaxed text-ink-300">
              <p>
                {mlMethod ? (
                  <>
                    Scored on operations that look like its training data, the classifier is nearly perfect (F1 <strong className="font-semibold text-ink-50">{mlMethod.f1.toFixed(2)}</strong>). That number is the trap: it has learned
                    the shapes our generator produces.
                  </>
                ) : (
                  'Scored on operations that look like its training data, a classifier looks nearly perfect. That number is the trap: it has learned the shapes of the training set.'
                )}
              </p>
              <p>
                So we retrain it without one attack category at a time and ask what it catches. {failing > 0 ? `For ${failing} of ${rows.length} categories its recall falls below 50%. ` : ''}The transparent rules do not have that problem,
                because they encode what the attack <em>is</em>, not what it looked like. The shipped score blends both, and the blend weight is chosen on these withheld categories, not on the flattering in-distribution number.
              </p>
              <p className="text-[13px] text-ink-400">Synthetic operations from one fictional schema, labelled by the generator. Treat the pattern as the finding, not the percentages.</p>
            </div>
          </div>

          <figure ref={ref} aria-label="Recall on attack categories withheld from training" className="min-w-0">
            {rows.length > 0 ? (
              <>
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-line pb-2.5 text-[12px] text-ink-300">
                  <span className="flex items-center gap-2">
                    <i className="inline-block h-3 w-3 rounded-full border-2 border-block" /> Model alone
                  </span>
                  <span className="flex items-center gap-2">
                    <i className="inline-block h-2.5 w-2.5 rotate-45 bg-throttle" /> Rules
                  </span>
                  <span className="flex items-center gap-2">
                    <i className="inline-block h-3 w-3 rounded-full bg-white" /> Rules + model
                  </span>
                </div>
                <div className="num mt-2.5 flex justify-between text-[11px] text-ink-400">
                  <span>0%</span>
                  <span>recall on the withheld category</span>
                  <span>100%</span>
                </div>
                <ul className="divide-y divide-line-faint">
                  {rows.map((r, i) => (
                    <Dumbbell key={r.name} row={r} seen={seen} i={i} />
                  ))}
                </ul>
                <Caption>Leave-one-attack-category-out on the test split: the model is retrained without the named category, then scored on that category&apos;s held-out operations.</Caption>
              </>
            ) : (
              <Pending state={state} what="This chart" />
            )}
          </figure>
        </div>
      </div>
    </section>
  );
}
