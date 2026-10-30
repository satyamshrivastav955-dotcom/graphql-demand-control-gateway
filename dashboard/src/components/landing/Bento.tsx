import { ReactNode, useState } from 'react';
import { DEFAULT_LIMITS, DEMO } from '../../data/demo';
import type { DemoSample } from '../../data/demo';
import { useInView } from '../../hooks/motion';
import { DECISION_STYLE, fmtInt } from '../../lib';
import RuleWaterfall from '../RuleWaterfall';

const byId = (id: string) => DEMO.samples.find((s) => s.id === id) as DemoSample;

function Tile({ n, title, children, className = '', body }: { n: string; title: string; body: string; children: ReactNode; className?: string }) {
  return (
    <article className={`flex min-w-0 flex-col bg-ink-950 p-5 sm:p-6 ${className}`}>
      <div className="flex items-baseline gap-3">
        <span className="num font-mono text-[12px] text-ink-400">{n}</span>
        <h3 className="text-[16px] font-semibold tracking-[-0.02em] text-ink-50">{title}</h3>
      </div>
      <p className="mt-2 max-w-[44ch] text-[13.5px] leading-relaxed text-ink-300">{body}</p>
      <div className="mt-5 flex-1">{children}</div>
    </article>
  );
}

/** Depth versus cost for every recorded sample: a fragment bomb is invisible to a depth limit. */
function DepthVsCost({ seen }: { seen: boolean }) {
  const maxCost = Math.log10(100000);
  return (
    <div>
      <div className="mb-2 grid grid-cols-[6rem_1fr_1fr] sm:grid-cols-[9rem_1fr_1fr] gap-x-4 text-[11.5px] text-ink-400">
        <span />
        <span>Depth (limit {DEFAULT_LIMITS.depth})</span>
        <span>Cost (limit {fmtInt(DEFAULT_LIMITS.cost)}, log scale)</span>
      </div>
      <ul className="space-y-2.5">
        {DEMO.samples.map((s, i) => {
          const depth = s.features.max_depth ?? 0;
          const cost = s.features.complexity_score ?? 0;
          const dOver = depth > DEFAULT_LIMITS.depth;
          const cOver = cost > DEFAULT_LIMITS.cost;
          const dW = Math.min(1, depth / 20) * 100;
          const cW = (Math.log10(Math.max(1, cost)) / maxCost) * 100;
          return (
            <li key={s.id} className="grid grid-cols-[6rem_1fr_1fr] sm:grid-cols-[9rem_1fr_1fr] items-center gap-x-4">
              <span className="truncate text-[12.5px] text-ink-200">{s.title}</span>
              <div className="grid grid-cols-[1fr_3rem] items-center gap-x-2">
                <div className="relative h-2.5 rounded-[2px] bg-white/[0.07]" aria-hidden>
                  <div className={`h-full rounded-[2px] transition-[width] duration-700 ease-out ${dOver ? 'bg-block' : 'bg-ink-300'}`} style={{ width: seen ? `${dW}%` : 0, transitionDelay: `${i * 70}ms` }} />
                  <div className="absolute inset-y-[-3px] w-px bg-white/50" style={{ left: `${(DEFAULT_LIMITS.depth / 20) * 100}%` }} />
                </div>
                <span className={`num text-right text-[12px] ${dOver ? 'text-block' : 'text-ink-300'}`}>{depth}</span>
              </div>
              <div className="grid grid-cols-[1fr_3.6rem] items-center gap-x-2">
                <div className="relative h-2.5 rounded-[2px] bg-white/[0.07]" aria-hidden>
                  <div className={`h-full rounded-[2px] transition-[width] duration-700 ease-out ${cOver ? 'bg-block' : 'bg-ink-300'}`} style={{ width: seen ? `${cW}%` : 0, transitionDelay: `${i * 70 + 120}ms` }} />
                  <div className="absolute inset-y-[-3px] w-px bg-white/50" style={{ left: `${(Math.log10(DEFAULT_LIMITS.cost) / maxCost) * 100}%` }} />
                </div>
                <span className={`num text-right text-[12px] ${cOver ? 'text-block' : 'text-ink-300'}`}>{fmtInt(cost)}</span>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 text-[12.5px] leading-relaxed text-ink-400">
        The fragment bomb is two levels deep, so a depth limit never sees it. Its resolved cost is <span className="num text-block">{fmtInt(byId('fragments').features.complexity_score)}</span>.
      </p>
    </div>
  );
}

function FeatureLedger({ s }: { s: DemoSample }) {
  const rows = Object.entries(s.features);
  return (
    <div>
      <p className="mb-2 text-[12px] text-ink-400">
        Extracted from <span className="text-ink-200">{s.title.toLowerCase()}</span>
      </p>
      <dl className="divide-y divide-line-faint rounded-md border border-line">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
            <dt className="truncate font-mono text-[12px] text-ink-300">{k}</dt>
            <dd className="num text-[13px] font-medium text-ink-50">{fmtInt(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function EnforceLog({ seen }: { seen: boolean }) {
  const status = (s: DemoSample) => (s.decision === 'BLOCK' ? 403 : s.decision === 'THROTTLE' ? '200/429' : 200);
  return (
    <div className="overflow-hidden rounded-md border border-line bg-ink-950 font-mono text-[12.5px]" role="table" aria-label="Recorded decisions">
      {DEMO.samples.map((s, i) => {
        const st = DECISION_STYLE[s.decision];
        return (
          <div
            key={s.id}
            role="row"
            className={`grid grid-cols-[3.4rem_5rem_3.4rem_1fr] items-center gap-x-3 border-b border-line-faint px-3 py-3 last:border-0 ${seen ? 'animate-grow' : 'opacity-0'}`}
            style={{ animationDelay: `${i * 110}ms` }}
          >
            <span role="cell" className="num text-ink-400">{status(s)}</span>
            <span role="cell" className={`font-semibold ${st.text}`}>
              {s.decision}
            </span>
            <span role="cell" className="num text-ink-200">{s.score % 1 === 0 ? s.score : s.score.toFixed(1)}</span>
            <span role="cell" className="truncate text-ink-300">
              {s.limit_violations[0] ?? s.explanations.find((e) => e.points > 0)?.rule.replace(/_/g, ' ') ?? 'no rule fired'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ShadowToggle() {
  const [shadow, setShadow] = useState(false);
  const rows = [byId('aliases'), byId('nesting'), byId('ordinary')];
  const outcome = (s: DemoSample) => {
    if (s.decision === 'ALLOW') return { code: '200', text: 'forwarded', tone: 'text-allow' };
    if (shadow) return { code: '200', text: `forwarded · would ${s.decision.toLowerCase()}`, tone: 'text-throttle' };
    return s.decision === 'BLOCK' ? { code: '403', text: 'blocked', tone: 'text-block' } : { code: '429', text: 'after quota', tone: 'text-throttle' };
  };
  return (
    <div>
      <div className="flex items-center justify-between gap-4 rounded-md border border-line bg-ink-900 px-3 py-2.5">
        <div>
          <div className="text-[13px] font-medium text-ink-50" id="shadow-label">Shadow mode</div>
          <div className="text-[12px] text-ink-400">{shadow ? 'Record the decision, forward everything' : 'Enforce the decision'}</div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={shadow}
          aria-labelledby="shadow-label"
          onClick={() => setShadow((v) => !v)}
          className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors ${shadow ? 'border-throttle/60 bg-throttle/25' : 'border-line-strong bg-white/[0.08]'}`}
        >
          <span className={`absolute left-[3px] top-[3px] h-3 w-3 rounded-full transition-transform ${shadow ? 'translate-x-4 bg-throttle' : 'bg-ink-200'}`} />
        </button>
      </div>
      <ul className="mt-3 divide-y divide-line-faint font-mono text-[12.5px]">
        {rows.map((s) => {
          const o = outcome(s);
          return (
            <li key={s.id} className="grid grid-cols-[1fr_auto] items-baseline gap-3 py-1.5">
              <span className="truncate text-ink-300">{s.title}</span>
              <span className={`num ${o.tone}`}>
                {o.code} {o.text}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const PROM = `# counters and histograms: names and labels are exact, values are yours
sentinel_requests_total{decision="BLOCK",enforced="blocked"} <count>
sentinel_hard_limit_violations_total{limit="max_depth"} <count>
sentinel_analysis_duration_seconds_bucket{le="0.01"} <count>
sentinel_model_loaded 1`;

function hook(): string {
  const s = byId('aliases');
  const rules = s.explanations.filter((e) => e.points > 0 || e.rule === 'hard_limit').map((e) => e.rule);
  return JSON.stringify(
    {
      text: `GraphQL Sentinel: ${s.decision} (blocked) from <client ip>, score ${s.score}, rules: ${rules.join(', ')}`,
      event: { decision: s.decision, risk_tier: s.risk_tier, score: s.score, limit_violations: s.limit_violations },
    },
    null,
    2,
  );
}

export default function Bento() {
  const [ref, seen] = useInView<HTMLDivElement>(0.12);
  return (
    <section id="how" aria-labelledby="how-h" className="scroll-mt-20 border-t border-line">
      <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="max-w-2xl">
          <h2 id="how-h" className="h-section">
            Four steps, no black box.
          </h2>
          <p className="lead mt-5 text-[16px]">
            Parse and resolve, extract features, score, enforce. Everything in the tiles below is drawn from the recorded output of the shipped engine, not from a mock-up.
          </p>
        </div>

        <div ref={ref} className="mt-12 grid grid-cols-[minmax(0,1fr)] gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-12">
          <Tile n="01" title="Parse and resolve" body="The operation is parsed under a token budget, the right operation is selected, and fragments are resolved once each, so a fragment bomb is analysed in linear time." className="lg:col-span-7">
            <DepthVsCost seen={seen} />
          </Tile>
          <Tile n="02" title="Extract features" body="Sixteen numeric features describe structure, cost and meaning. This is what the rules and the model both read." className="lg:col-span-5">
            <FeatureLedger s={byId('aliases')} />
          </Tile>
          <Tile n="03" title="Score" body="Named rules add points that sum to the rule score; a checksummed model adds one documented term. Nothing is hidden inside the number." className="lg:col-span-5">
            <RuleWaterfall explanations={byId('nesting').explanations} ruleScore={byId('nesting').rule_score} mlScore={byId('nesting').ml_score} score={byId('nesting').score} />
          </Tile>
          <Tile n="04" title="Enforce" body="Risk tiers map to allow, throttle or block in the backend. Blocked operations never reach your upstream; throttled clients get 429 past a small quota." className="lg:col-span-7">
            <EnforceLog seen={seen} />
          </Tile>
          <Tile n="+" title="Roll out safely" body="Shadow mode records the real decision but forwards everything, so a policy can be tuned on live traffic first." className="lg:col-span-4">
            <ShadowToggle />
          </Tile>
          <Tile n="+" title="Metrics" body="Prometheus text at /metrics, behind the management token." className="lg:col-span-4">
            <pre tabIndex={0} className="whitespace-pre-wrap break-words rounded-md border border-line bg-ink-950 p-3 font-mono text-[11.5px] leading-[1.7] text-ink-300">
              <code>{PROM}</code>
            </pre>
          </Tile>
          <Tile n="+" title="Alerts" body="Slack-compatible webhook for blocked operations; the URL is a secret and never logged." className="lg:col-span-4">
            <pre tabIndex={0} className="whitespace-pre-wrap break-words rounded-md border border-line bg-ink-950 p-3 font-mono text-[11.5px] leading-[1.7] text-ink-300">
              <code>{hook()}</code>
            </pre>
          </Tile>
        </div>
      </div>
    </section>
  );
}
