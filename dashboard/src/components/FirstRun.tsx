import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, Copy, Loader2, Send } from 'lucide-react';
import { api, API_BASE } from '../api/client';
import { useCopy } from '../hooks/motion';
import { curlFor } from '../lib';

/** A copyable shell block for the dark dashboard surface. */
export function CopyCode({ code, label = 'Copy' }: { code: string; label?: string }) {
  const { copied, copy } = useCopy();
  return (
    <div className="relative overflow-hidden rounded-md border border-line bg-ink-950 text-left">
      <pre tabIndex={0} className="overflow-x-auto p-3.5 pr-24 font-mono text-[12.5px] leading-[1.65] text-ink-100">
        <code>{code}</code>
      </pre>
      <button
        type="button"
        onClick={() => copy(code)}
        className="absolute right-2 top-2 inline-flex h-7 items-center gap-1.5 rounded-md border border-line-strong bg-ink-850 px-2 text-[12px] text-ink-200 hover:bg-ink-800 hover:text-ink-50"
        aria-label={copied ? 'Copied' : `${label} to clipboard`}
      >
        {copied ? <Check className="h-3.5 w-3.5 text-allow" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
        <span aria-live="polite">{copied ? 'Copied' : label}</span>
      </button>
    </div>
  );
}

/** First-run guidance: how to send traffic, plus a button that sends one harmless real request through the gateway. */
export default function FirstRun({ title, onSent }: { title: string; onSent?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const origin = API_BASE || (typeof window !== 'undefined' ? window.location.origin : '');
  const curl = curlFor('{ __typename }', { origin });

  const send = async () => {
    setBusy(true);
    setResult(null);
    try {
      const out = await api.proxy({ query: 'query Ping { __typename }' }, 'dashboard-test');
      const sec = out.body.extensions?.security;
      setResult(sec ? `${sec.decision}: ${sec.enforced ?? ''}`.trim() : `HTTP ${out.status}`);
      onSent?.();
    } catch (e) {
      setResult((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center">
      <div>
        <p className="text-[18px] font-semibold tracking-[-0.02em] text-ink-50">{title}</p>
        <p className="mt-2 max-w-sm text-[13.5px] leading-relaxed text-ink-300">
          Every request sent to <code className="font-mono text-[12.5px] text-ink-100">/graphql-proxy</code> becomes a security event here. Send one from your shell, or let the dashboard send a harmless test request.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button type="button" className="btn-primary" onClick={send} disabled={busy}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Send className="h-3.5 w-3.5" aria-hidden />}
            Send a test request
          </button>
          <Link to="/app/analyze" className="btn-secondary">
            Open the analyzer
          </Link>
        </div>
        {result && (
          <p role="status" className="mt-4 text-[13px] text-ink-200">
            Gateway answered <span className="font-mono text-ink-50">{result}</span>. It appears in the list within seconds.
          </p>
        )}
      </div>
      <CopyCode code={curl} label="Copy curl" />
    </div>
  );
}
