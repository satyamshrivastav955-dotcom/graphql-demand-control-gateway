import { doc } from './SiteChrome';

const CONTROLS = [
  ['Management API behind a token', 'Constant-time comparison, per-IP lockout after repeated failures, rate limits, and a fail-closed 503 when no token is set.'],
  ['Hard limits that cannot be scored away', 'Depth, aliases, cost, tokens, size and fragment cycles always block, whatever the model says.'],
  ['No fake upstream responses', 'Without an upstream the gateway answers 503. Upstream errors never leak hostnames or bodies.'],
  ['Sensitive data kept out of storage', 'Variables are never stored and credential literals in queries are redacted before an event is written.'],
  ['Bounded memory everywhere', 'Rate-limit state, client history, live streams and stored events all have fixed ceilings.'],
  ['A model you can verify', 'The classifier loads only if its checksum and feature list match its metadata; otherwise the rules run alone.'],
];

const NOT = [
  ['Not a WAF', 'It reads GraphQL operations. It does not stop injection inside resolvers or fix broken authorisation.'],
  ['Evaluated on synthetic data', 'One fictional schema and generator-assigned labels. Run it on your own traffic before trusting a threshold.'],
  ['One shared token', 'No roles, SSO or per-user audit yet. Treat the dashboard as an operator tool.'],
  ['Single process', 'Rate-limit and behaviour state live in memory. Run one replica per upstream.'],
  ['Docker stack not yet verified in CI', 'The images and Compose file are reviewed but have not been run end to end. The verification checklist is in the deployment guide.'],
];

function List({ title, items, tone }: { title: string; items: string[][]; tone: 'ok' | 'warn' }) {
  return (
    <div>
      <h3 className="flex items-center gap-2 border-b border-line pb-3 text-[13px] font-medium text-ink-50">
        <span className={`h-1.5 w-1.5 rounded-full ${tone === 'ok' ? 'bg-allow' : 'bg-throttle'}`} aria-hidden />
        {title}
      </h3>
      <dl className="divide-y divide-line-faint">
        {items.map(([t, d]) => (
          <div key={t} className="grid gap-1 py-3.5 sm:grid-cols-[13rem_1fr] sm:gap-6">
            <dt className="text-[14px] font-medium text-ink-50">{t}</dt>
            <dd className="text-[13.5px] leading-relaxed text-ink-300">{d}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function Trust() {
  return (
    <section id="trust" aria-labelledby="trust-h" className="scroll-mt-20 border-t border-line bg-ink-900/40">
      <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8 sm:py-28">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <h2 id="trust-h" className="h-section max-w-[20ch]">
            What it does, and what it does not.
          </h2>
          <p className="rounded-md border border-line-strong px-3 py-1.5 text-[12.5px] text-ink-200">Status: v1.0 pre-release</p>
        </div>

        <div className="mt-12 grid gap-12 lg:grid-cols-2 lg:gap-16">
          <List title="Tested controls" items={CONTROLS} tone="ok" />
          <List title="Known limits" items={NOT} tone="warn" />
        </div>

        <p className="mt-10 max-w-3xl text-[14px] leading-relaxed text-ink-300">
          Read the{' '}
          <a className="text-ink-50 underline decoration-white/30 underline-offset-4 hover:decoration-white" href={doc('docs/threat-model.md')} target="_blank" rel="noreferrer">
            threat model
          </a>{' '}
          and the{' '}
          <a className="text-ink-50 underline decoration-white/30 underline-offset-4 hover:decoration-white" href={doc('docs/deployment.md')} target="_blank" rel="noreferrer">
            deployment review
          </a>{' '}
          before exposing it. Released under the{' '}
          <a className="text-ink-50 underline decoration-white/30 underline-offset-4 hover:decoration-white" href={doc('LICENSE')} target="_blank" rel="noreferrer">
            MIT licence
          </a>
          .
        </p>
      </div>
    </section>
  );
}
