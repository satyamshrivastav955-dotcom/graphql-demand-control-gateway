import { Suspense, lazy, useMemo } from 'react';
import { ArrowDown, ArrowRight } from 'lucide-react';
import { DEMO } from '../data/demo';
import { fmtInt } from '../lib';
import { api } from '../api/client';
import { useApi } from '../hooks/useApi';
import { DemoConsole, EngineReadout, useDemoPlayer } from '../components/landing/Demo';
import { CopyButton } from '../components/landing/QuickStart';
import { Footer, Nav, REPO_URL } from '../components/landing/SiteChrome';

// Everything below the hero is a separate chunk that loads right after first paint, keeping the hero's startup work small.
const BelowTheFold = lazy(() => import('../components/landing/BelowTheFold'));

export { REPO_URL };

function Hero() {
  const player = useDemoPlayer();
  const bomb = DEMO.samples.find((s) => s.id === 'fragments');
  const bytes = useMemo(() => (bomb ? new Blob([bomb.query]).size : 0), [bomb]);
  const d = (ms: number) => ({ animationDelay: `${ms}ms` });
  return (
    <section aria-labelledby="hero-h" className="relative">
      <div className="bg-grid pointer-events-none absolute inset-x-0 top-0 h-[640px] opacity-60 [mask-image:linear-gradient(to_bottom,black,transparent)]" aria-hidden />
      <div className="relative mx-auto max-w-[1200px] px-5 pb-10 pt-12 sm:px-8 sm:pt-16 lg:pt-20">
        <div className="grid grid-cols-[minmax(0,1fr)] items-center gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12">
          <div>
            <p className="animate-rise inline-flex items-center gap-2 text-[13px] text-ink-300" style={d(0)}>
              <span className="h-1.5 w-1.5 rounded-full bg-allow" aria-hidden />
              Open source · MIT · v1.0 pre-release
            </p>
            <h1 id="hero-h" className="h-display animate-rise mt-5" style={d(60)}>
              Secure the operation, not just the request.
            </h1>
            <p className="lead animate-rise mt-6 max-w-[34rem]" style={d(120)}>
              {bomb ? (
                <>
                  A <span className="num text-ink-50">{fmtInt(bytes)}-byte</span> GraphQL request can ask your server to execute{' '}
                  <span className="num text-ink-50">{fmtInt(bomb.features.field_count)}</span> fields. Sentinel reads every operation before it reaches your API, scores it with rules you can read and a model you can check, and enforces allow, throttle or block.
                </>
              ) : (
                'Sentinel reads every GraphQL operation before it reaches your API, scores it with rules you can read and a model you can check, and enforces allow, throttle or block.'
              )}
            </p>
            <div className="animate-rise mt-8 flex flex-wrap items-center gap-2.5" style={d(180)}>
              <a href="#demo" className="btn-primary btn-lg">
                See it decide <ArrowDown className="h-4 w-4" aria-hidden />
              </a>
              <a href="#start" className="btn-secondary btn-lg">
                Run it yourself <ArrowRight className="h-4 w-4" aria-hidden />
              </a>
            </div>
            <div className="animate-rise mt-9 max-w-[34rem]" style={d(240)}>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-line-strong bg-ink-900 py-1.5 pl-3.5 pr-1.5">
                <code className="min-w-0 truncate font-mono text-[12.5px] text-ink-100">
                  <span className="select-none text-ink-400">$ </span>python scripts/dev.py
                </code>
                <CopyButton text="python scripts/dev.py" label="Copy" />
              </div>
              <p className="mt-2.5 text-[12.5px] text-ink-400">Self-hosted reverse proxy. MIT licence, no telemetry. Opens the demo on http://127.0.0.1:8000.</p>
            </div>
          </div>
          <div id="demo" className="animate-fade-up scroll-mt-20" style={d(200)}>
            <DemoConsole player={player} />
          </div>
        </div>
        <div className="mt-8 animate-fade-up" style={d(320)}>
          <EngineReadout player={player} />
        </div>
      </div>
    </section>
  );
}

export default function Landing() {
  const evaluation = useApi((s) => api.evaluation(s), []);
  return (
    <div className="min-h-screen bg-ink-950 text-ink-100">
      <a href="#main" className="sr-only z-50 rounded-md bg-white px-4 py-2 text-ink-950 focus:not-sr-only focus:fixed focus:left-4 focus:top-4">
        Skip to content
      </a>
      <Nav />
      <main id="main">
        <Hero />
        <Suspense fallback={<div aria-hidden className="min-h-[2600px]" />}>
          <BelowTheFold evaluation={evaluation} />
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}

export { REPO_URL as GITHUB_URL };
