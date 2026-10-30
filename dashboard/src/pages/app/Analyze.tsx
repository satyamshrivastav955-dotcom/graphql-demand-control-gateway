import { FormEvent, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { ArrowRight, Loader2, Play, Send } from 'lucide-react';
import { useEnforcement } from '../../hooks/enforcement';
import { api, ApiError, ProxyOutcome, QueryBody } from '../../api/client';
import type { AnalyzeResult, Decision, Enforced, Explanation, Tier } from '../../api/types';
import { fmtMs, fmtFixed, isShadow } from '../../lib';
import { DecisionBadge, TierBadge } from '../../components/ui/badges';
import { CodeBlock, EmptyState, ErrorState, PageHeader, Panel } from '../../components/ui/primitives';
import { CodeEditor, lineMarks } from '../../components/code';
import RuleWaterfall from '../../components/RuleWaterfall';
import TierScale from '../../components/TierScale';

export const PRESETS: { id: string; label: string; query: string }[] = [
  {
    id: 'benign',
    label: 'Ordinary query',
    query: `query Profile {\n  user(id: "42") {\n    name\n    posts(limit: 5) {\n      title\n    }\n  }\n}`,
  },
  {
    id: 'deep',
    label: 'Deep nesting',
    query: `query Deep {\n  user(id: "1") {\n    friends {\n      friends {\n        friends {\n          friends {\n            friends {\n              friends {\n                friends {\n                  friends {\n                    name\n                  }\n                }\n              }\n            }\n          }\n        }\n      }\n    }\n  }\n}`,
  },
  {
    id: 'alias',
    label: 'Alias batching',
    query: `query Batch {\n${Array.from({ length: 24 }, (_, i) => `  a${i}: user(id: "${i}") { name }`).join('\n')}\n}`,
  },
  {
    id: 'introspection',
    label: 'Introspection',
    query: `query IntrospectionQuery {\n  __schema {\n    types {\n      name\n      fields {\n        name\n      }\n    }\n  }\n}`,
  },
];

interface View {
  source: 'analyze' | 'gateway';
  decision: Decision;
  tier?: Tier;
  score?: number;
  ruleScore?: number;
  mlScore?: number | null;
  explanations: Explanation[];
  violations: string[];
  latency?: number;
  features?: Record<string, number>;
  wouldForward?: boolean;
  enforced?: Enforced;
  eventId?: string;
  status?: number;
  body?: unknown;
  message?: string;
  simulated?: boolean;
  shadow?: boolean;
}

const ENFORCED_TEXT: Record<Enforced, string> = {
  forwarded: 'Forwarded to the upstream and its response returned.',
  blocked: 'Blocked. The request never reached the upstream.',
  rate_limited: 'Rate limited. The request was not forwarded.',
  upstream_error: 'Allowed by policy, but the upstream failed to answer.',
  rejected: 'Rejected before analysis (invalid or oversized input).',
  simulated: 'Simulation mode: no upstream is configured, so nothing was forwarded.',
  shadow: 'Shadow mode: the decision above was recorded but not enforced, and the operation was forwarded to the upstream.',
};

function fromAnalyze(r: AnalyzeResult): View {
  return {
    source: 'analyze',
    decision: r.decision,
    tier: r.risk_tier,
    score: r.score,
    ruleScore: r.rule_score,
    mlScore: r.ml_score,
    explanations: r.explanations,
    violations: r.limit_violations,
    latency: r.latency_ms,
    features: r.features,
    wouldForward: r.would_forward,
  };
}

function fromProxy(o: ProxyOutcome): View {
  const sec = o.body.extensions?.security;
  const decision = sec?.decision ?? o.decisionHeader ?? 'ERROR';
  return {
    source: 'gateway',
    decision,
    tier: sec?.risk_tier,
    score: sec?.score,
    ruleScore: sec?.rule_score,
    mlScore: sec?.ml_score,
    explanations: sec?.explanations ?? [],
    violations: sec?.limit_violations ?? [],
    latency: sec?.latency_ms,
    enforced: sec?.enforced,
    eventId: sec?.event_id,
    status: o.status,
    body: o.body,
    simulated: sec?.simulated,
    shadow: isShadow(sec?.enforced, sec?.shadow),
    message: sec ? undefined : o.body.errors?.[0]?.message,
  };
}

export default function Analyze() {
  const location = useLocation();
  const preset = (location.state as { query?: string } | null)?.query;
  // Deep link: /app/analyze?example=deep&run=dry loads an example and runs a dry-run analysis.
  const [params] = useSearchParams();
  const example = PRESETS.find((p) => p.id === params.get('example'));
  const [query, setQuery] = useState(preset ?? example?.query ?? PRESETS[0].query);
  const [variables, setVariables] = useState('');
  const [operationName, setOperationName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | 'analyze' | 'gateway'>(null);
  const [result, setResult] = useState<View | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (preset) setQuery(preset);
  }, [preset]);

  const buildBody = (): QueryBody | null => {
    if (!query.trim()) {
      setFormError('Enter a GraphQL operation first.');
      return null;
    }
    const body: QueryBody = { query };
    if (variables.trim()) {
      try {
        const v = JSON.parse(variables);
        if (v === null || typeof v !== 'object' || Array.isArray(v)) throw new Error();
        body.variables = v;
      } catch {
        setFormError('Variables must be a valid JSON object.');
        return null;
      }
    }
    if (operationName.trim()) body.operationName = operationName.trim();
    setFormError(null);
    return body;
  };

  const run = async (mode: 'analyze' | 'gateway') => {
    const body = buildBody();
    if (!body || busy) return;
    setBusy(mode);
    setError(null);
    try {
      const view = mode === 'analyze' ? fromAnalyze(await api.analyze(body)) : fromProxy(await api.proxy(body));
      setResult(view);
      requestAnimationFrame(() => resultRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' }));
    } catch (e) {
      setResult(null);
      if (e instanceof ApiError && e.status === 400) {
        setError(e);
      } else {
        setError(e instanceof ApiError ? e : new ApiError((e as Error).message, 0));
      }
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (params.get('run') === 'dry') run('analyze');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run('analyze');
  };

  const marks = result && result.source === 'analyze' ? lineMarks(query, result.explanations.map((x) => x.rule)) : result ? lineMarks(query, result.explanations.map((x) => x.rule)) : undefined;

  return (
    <>
      <PageHeader
        title="Analyze"
        description="Submit a GraphQL operation to the live gateway. A dry run analyses it without forwarding; sending it through the gateway enforces the decision and records an event."
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <form onSubmit={submit} className="space-y-3" aria-label="Operation editor">
          <Panel
            title="Operation"
            hint={marks && marks.size > 0 ? 'Highlighted lines triggered rules' : undefined}
            actions={
              <select
                aria-label="Load an example"
                className="field h-7 w-auto pr-7 text-[12.5px]"
                value=""
                onChange={(e) => {
                  const p = PRESETS.find((x) => x.id === e.target.value);
                  if (p) {
                    setQuery(p.query);
                    setFormError(null);
                  }
                }}
              >
                <option value="">Load example…</option>
                {PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            }
          >
            <div className="p-3">
              <CodeEditor label="GraphQL operation" value={query} onChange={setQuery} onRun={() => run('analyze')} marks={marks} />
            </div>
          </Panel>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="vars" className="mb-1.5 block text-[12.5px] font-medium text-ink-300">
                Variables (JSON, optional)
              </label>
              <textarea id="vars" className="field h-[72px] font-mono text-[12px]" placeholder='{"id": "42"}' spellCheck={false} value={variables} onChange={(e) => setVariables(e.target.value)} />
            </div>
            <div>
              <label htmlFor="opname" className="mb-1.5 block text-[12.5px] font-medium text-ink-300">
                Operation name (optional)
              </label>
              <input id="opname" className="field font-mono text-[12px]" value={operationName} onChange={(e) => setOperationName(e.target.value)} placeholder="Profile" />
            </div>
          </div>

          {formError && (
            <p role="alert" className="rounded-md border border-block/30 bg-block/[0.08] px-3 py-2 text-[13px] text-block">
              {formError}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className="btn-primary" disabled={busy !== null}>
              {busy === 'analyze' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
              Analyze (dry run)
            </button>
            <button type="button" className="btn-secondary" disabled={busy !== null} onClick={() => run('gateway')}>
              {busy === 'gateway' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Send className="h-3.5 w-3.5" aria-hidden />}
              Send through gateway
            </button>
            <span className="ml-1 hidden items-center gap-1 text-[12px] text-ink-400 sm:inline-flex">
              <span className="kbd">Ctrl</span>
              <span className="kbd">↵</span> to analyze
            </span>
          </div>
          <p className="text-[12.5px] leading-relaxed text-ink-400">
            <strong className="font-medium text-ink-300">Dry run</strong> never reaches the upstream and is not stored.{' '}
            <strong className="font-medium text-ink-300">Send through gateway</strong> enforces the decision, forwards allowed operations and records a security event.
          </p>
        </form>

        <div ref={resultRef} aria-live="polite" className="min-w-0">
          {busy && (
            <Panel>
              <div role="status" className="space-y-3 p-5">
                <span className="sr-only">{busy === 'analyze' ? 'Analyzing operation…' : 'Sending through gateway…'}</span>
                <div className="skeleton h-5 w-28 animate-shimmer rounded" aria-hidden />
                <div className="skeleton h-9 w-40 animate-shimmer rounded" aria-hidden />
                <div className="skeleton h-1.5 w-full animate-shimmer rounded" aria-hidden />
                <div className="skeleton h-3.5 w-2/3 animate-shimmer rounded" aria-hidden />
              </div>
            </Panel>
          )}
          {!busy && error && (
            <Panel>
              {error.status === 400 ? (
                <div role="alert" className="p-5">
                  <p className="text-[14px] font-medium text-fault">Not a valid GraphQL operation</p>
                  <p className="mt-1 font-mono text-[12.5px] text-ink-200">{error.message}</p>
                </div>
              ) : (
                <ErrorState error={error} onRetry={() => run('analyze')} compact />
              )}
            </Panel>
          )}
          {!busy && !error && !result && (
            <Panel>
              <EmptyState title="No result yet">Run a dry-run analysis to see the risk score, extracted features and the rules that fired.</EmptyState>
            </Panel>
          )}
          {!busy && !error && result && <ResultView v={result} />}
        </div>
      </div>
    </>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div title={hint} className="min-w-0">
      <div className="text-[12px] text-ink-400">{label}</div>
      <div className="num mt-0.5 text-[18px] font-semibold tracking-[-0.02em] text-ink-50">{value}</div>
    </div>
  );
}

export function ResultView({ v }: { v: View }) {
  const enforcement = useEnforcement();
  const [showBody, setShowBody] = useState(false);
  return (
    <div className="animate-fade-up space-y-3" data-testid="result">
      <Panel>
        <div className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <DecisionBadge decision={v.decision} size="lg" shadow={v.shadow} />
              {v.tier && <TierBadge tier={v.tier} />}
            </div>
            <span className="text-[12px] text-ink-400">{v.source === 'analyze' ? 'Dry run' : `Gateway · HTTP ${v.status}`}</span>
          </div>
          {v.score !== undefined && (
            <div className="mt-4">
              <div className="mb-2.5 flex items-baseline justify-between">
                <span className="text-[13px] text-ink-300">Risk score</span>
                <span className="num text-[30px] font-semibold leading-none tracking-[-0.04em] text-ink-50">
                  {fmtFixed(v.score, 1)}
                  <span className="ml-1 text-[13px] font-normal tracking-normal text-ink-400">/ 100</span>
                </span>
              </div>
              <TierScale score={v.score} />
            </div>
          )}
          <div className="mt-4 grid grid-cols-3 gap-4 border-t border-line pt-3.5">
            <Metric label="Rule score" value={fmtFixed(v.ruleScore, 1)} hint="Score from the deterministic rule engine (0-100)" />
            <Metric label="ML score" value={v.mlScore === null || v.mlScore === undefined ? 'n/a' : fmtFixed(v.mlScore, 3)} hint="Model probability (0-1); n/a if no model is loaded" />
            <Metric label="Analysis time" value={fmtMs(v.latency)} hint="Parse + feature extraction + scoring" />
          </div>
          {v.source === 'analyze' && v.wouldForward !== undefined && (
            <p className="mt-3.5 text-[13px] text-ink-300">
              {v.wouldForward || enforcement === 'shadow' ? 'This operation would be forwarded to the upstream.' : 'This operation would not be forwarded to the upstream.'}
            </p>
          )}
          {(v.shadow ? ENFORCED_TEXT.shadow : v.enforced && ENFORCED_TEXT[v.enforced]) && (
            <p className="mt-3.5 text-[13px] text-ink-300">{v.shadow ? ENFORCED_TEXT.shadow : ENFORCED_TEXT[v.enforced as Enforced]}</p>
          )}
          {v.source === 'analyze' && enforcement === 'shadow' && (
            <p className="mt-3.5 text-[13px] text-ink-300">The gateway is in shadow mode: it records this decision but forwards every operation regardless.</p>
          )}
          {v.simulated && (
            <p className="mt-3 rounded-md border border-throttle/30 bg-throttle/[0.08] px-3 py-2 text-[13px] text-throttle">
              Simulation mode: the response body below is not from a real upstream.
            </p>
          )}
          {v.message && <p className="mt-3 text-[13px] text-ink-200">Gateway message: {v.message}</p>}
          {v.eventId && (
            <Link to={`/app/events/${encodeURIComponent(v.eventId)}`} className="mt-3.5 inline-flex items-center gap-1.5 text-[13px] text-ink-100 underline decoration-white/30 underline-offset-4 hover:decoration-white">
              Open recorded event <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          )}
        </div>
      </Panel>

      {v.violations.length > 0 && (
        <Panel title="Limit violations">
          <ul className="divide-y divide-line-faint">
            {v.violations.map((x) => (
              <li key={x} className="px-4 py-2 font-mono text-[12.5px] text-block">
                {x}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="Why this decision" hint="Rules that contributed to the score">
        {v.explanations.length ? (
          <RuleWaterfall explanations={v.explanations} ruleScore={v.ruleScore} mlScore={v.mlScore} score={v.score} />
        ) : (
          <EmptyState title="No rules fired">The operation stayed within every rule threshold.</EmptyState>
        )}
      </Panel>

      {v.features && Object.keys(v.features).length > 0 && (
        <Panel title="Extracted features">
          <dl className="grid grid-cols-2 gap-x-5 px-4 py-1.5 sm:grid-cols-3">
            {Object.entries(v.features).map(([k, val]) => (
              <div key={k} className="flex items-baseline justify-between gap-2 border-b border-line-faint py-1.5">
                <dt className="truncate font-mono text-[11.5px] text-ink-400" title={k}>
                  {k}
                </dt>
                <dd className="num text-[13px] font-medium text-ink-50">{Number.isInteger(val) ? val : fmtFixed(val, 3)}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      )}

      {v.body !== undefined && (
        <Panel
          title="Raw gateway response"
          actions={
            <button className="text-[12.5px] text-ink-300 hover:text-ink-50" onClick={() => setShowBody((s) => !s)} aria-expanded={showBody}>
              {showBody ? 'Hide' : 'Show'}
            </button>
          }
        >
          {showBody && (
            <div className="p-3">
              <CodeBlock code={JSON.stringify(v.body, null, 2)} />
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
