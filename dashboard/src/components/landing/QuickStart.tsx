import { useRef, useState, KeyboardEvent } from 'react';
import { Check, Copy } from 'lucide-react';
import { useCopy } from '../../hooks/motion';

const REPO = 'https://github.com/satyamshrivastav955-dotcom/GraphQL-Sentinel';

export const SNIPPETS = [
  {
    id: 'local',
    label: 'Local',
    note: 'Python 3.12+ and Node 20+. Builds the dashboard once, then serves the landing page, dashboard and gateway on one port. Prints a session token for the dashboard.',
    code: `git clone ${REPO}
cd GraphQL-Sentinel
pip install -r backend/requirements.txt
python scripts/dev.py
# open http://127.0.0.1:8000   (upstream demo on :8001)`,
  },
  {
    id: 'docker',
    label: 'Docker Compose',
    note: 'Gateway, dashboard and a demo upstream. The Compose stack has not yet been verified in CI; run the checklist in docs/deployment.md first.',
    code: `cp .env.example .env
# set SENTINEL_API_TOKEN in .env (16+ characters)
docker compose up --build
# dashboard + gateway: http://localhost:8080`,
  },
  {
    id: 'call',
    label: 'Send a request',
    note: 'The gateway speaks plain GraphQL over HTTP. Clients keep their own Authorization header; it is passed to your upstream.',
    code: `curl -s localhost:8000/graphql-proxy \\
  -H 'content-type: application/json' \\
  -d '{"query":"{ users(first: 2) { name } }"}'

# 200 -> the upstream's real response, plus extensions.security
# 403 -> blocked, never forwarded     429 -> throttled`,
  },
  {
    id: 'config',
    label: 'Protect your API',
    note: 'Everything is environment-driven. The management token is required; client keys are optional.',
    code: `SENTINEL_UPSTREAM_URL=https://api.internal.example/graphql
SENTINEL_API_TOKEN=<32+ random characters>   # dashboard + management API
SENTINEL_GATEWAY_KEYS=<key1>,<key2>          # optional: require X-API-Key on /graphql-proxy
SENTINEL_ENFORCEMENT=shadow                  # optional: record decisions, enforce nothing yet`,
  },
] as const;

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const { copied, copy } = useCopy();
  return (
    <button
      type="button"
      onClick={() => copy(text)}
      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-ink-850 px-2.5 text-[12.5px] text-ink-200 transition-colors hover:bg-ink-800 hover:text-ink-50"
      aria-label={copied ? 'Copied' : `${label} to clipboard`}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-allow" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      <span aria-live="polite">{copied ? 'Copied' : label}</span>
    </button>
  );
}

function Code({ code }: { code: string }) {
  return (
    <pre tabIndex={0} className="overflow-x-auto px-4 py-4 font-mono text-[12.5px] leading-[1.75] text-ink-100">
      <code>
        {code.split('\n').map((raw, i) => (
          <div key={i} className={raw.trimStart().startsWith('#') ? 'text-ink-400' : ''}>
            {raw || ' '}
          </div>
        ))}
      </code>
    </pre>
  );
}

const STEPS = [
  ['Point clients at the gateway', 'It is a reverse proxy: one URL change, no SDK, no agent in your services.'],
  ['Start in shadow mode', 'Record the real decisions without enforcing anything, and review what would have been blocked.'],
  ['Enforce', 'Tune the limits from what you saw, switch enforcement on, and scrape /metrics.'],
];

export default function QuickStart() {
  const [id, setId] = useState<string>(SNIPPETS[0].id);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const cur = SNIPPETS.find((s) => s.id === id) ?? SNIPPETS[0];
  const onKey = (e: KeyboardEvent) => {
    const i = SNIPPETS.findIndex((s) => s.id === id);
    const n = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : null;
    if (n === null) return;
    e.preventDefault();
    const j = (n + SNIPPETS.length) % SNIPPETS.length;
    setId(SNIPPETS[j].id);
    tabs.current[j]?.focus();
  };
  return (
    <section id="start" aria-labelledby="start-h" className="scroll-mt-20 border-t border-line">
      <div className="mx-auto grid max-w-[1200px] gap-12 px-5 py-20 sm:px-8 sm:py-28 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <div>
          <h2 id="start-h" className="h-section max-w-[14ch]">
            In front of your API in minutes.
          </h2>
          <p className="lead mt-5 text-[16px]">Self-hosted and open source. There is no hosted service, no account and no telemetry.</p>
          <ol className="mt-8 space-y-0 border-t border-line">
            {STEPS.map(([t, d], i) => (
              <li key={t} className="grid grid-cols-[2rem_1fr] gap-x-2 border-b border-line py-4">
                <span className="num pt-0.5 font-mono text-[12px] text-ink-400">0{i + 1}</span>
                <div>
                  <div className="text-[14.5px] font-medium text-ink-50">{t}</div>
                  <p className="mt-1 text-[13.5px] leading-relaxed text-ink-300">{d}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
        <div className="min-w-0 self-start overflow-hidden rounded-lg border border-line-strong bg-ink-900">
          <div role="tablist" aria-label="Quick start" onKeyDown={onKey} className="flex gap-0.5 overflow-x-auto border-b border-line px-2 py-1.5">
            {SNIPPETS.map((s, i) => (
              <button
                key={s.id}
                ref={(el) => {
                  tabs.current[i] = el;
                }}
                role="tab"
                id={`qs-${s.id}`}
                aria-selected={s.id === id}
                aria-controls="qs-panel"
                tabIndex={s.id === id ? 0 : -1}
                onClick={() => setId(s.id)}
                className={`h-8 shrink-0 rounded-md px-3 text-[12.5px] font-medium transition-colors ${s.id === id ? 'bg-white/[0.1] text-ink-50' : 'text-ink-300 hover:bg-white/[0.05] hover:text-ink-50'}`}
              >
                {s.label}
              </button>
            ))}
          </div>
          <div id="qs-panel" role="tabpanel" aria-labelledby={`qs-${cur.id}`}>
            <p className="px-4 pt-3.5 text-[13px] leading-relaxed text-ink-300">{cur.note}</p>
            <Code code={cur.code} />
            <div className="flex justify-end border-t border-line px-3 py-2">
              <CopyButton text={cur.code} label="Copy commands" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
