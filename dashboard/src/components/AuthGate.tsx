import { FormEvent, ReactNode, useCallback, useEffect, useState } from 'react';
import { KeyRound, Loader2 } from 'lucide-react';
import { AUTH_EVENT, clearToken, getToken, setToken } from '../api/auth';
import { AccessState, probeAccess } from '../api/client';
import { Wordmark } from './Brand';

/**
 * Protects the dashboard routes. If the management API accepts the current credentials (a stored token, or none
 * when the server runs with auth disabled) the children render; otherwise a token prompt is shown.
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AccessState | 'checking'>('checking');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const check = useCallback(async () => {
    setState('checking');
    setState(await probeAccess());
  }, []);

  useEffect(() => {
    check();
    const onAuth = () => setState('unauthorized');
    window.addEventListener(AUTH_EVENT, onAuth);
    return () => window.removeEventListener(AUTH_EVENT, onAuth);
  }, [check]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const token = input.trim();
    if (!token) return;
    setBusy(true);
    setMessage(null);
    const result = await probeAccess(token);
    setBusy(false);
    if (result === 'ok') {
      setToken(token);
      setInput('');
      setState('ok');
    } else {
      setState(result);
      setMessage(
        result === 'unauthorized'
          ? 'That token was not accepted.'
          : result === 'locked'
            ? 'Too many failed attempts. Wait a few minutes and try again.'
            : result === 'unconfigured'
              ? 'The server has no management token configured.'
              : 'Cannot reach the Sentinel gateway.',
      );
    }
  };

  // An unreachable gateway is reported by each page's own error state, so it is not a reason to hide the UI.
  if (state === 'ok' || (state === 'unreachable' && !message)) return <>{children}</>;
  if (state === 'checking') {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink-950" role="status">
        <span className="sr-only">Checking access…</span>
        <div className="w-64 space-y-2.5" aria-hidden>
          <div className="skeleton h-3.5 animate-shimmer rounded" />
          <div className="skeleton h-3.5 w-2/3 animate-shimmer rounded" />
        </div>
      </main>
    );
  }

  const blocked = state === 'unconfigured';
  return (
    <main className="bg-grid flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <form onSubmit={submit} className="w-full max-w-[380px] space-y-5 rounded-lg border border-line-strong bg-ink-900 p-6" aria-label="Dashboard sign in">
        <Wordmark />
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.025em] text-ink-50">Dashboard access</h1>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-300">
            The management API is protected. Enter the access token configured on the server (
            <code className="font-mono text-[12px] text-ink-100">SENTINEL_API_TOKEN</code>). It is kept for this browser tab only.
          </p>
        </div>
        {blocked ? (
          <p role="alert" className="rounded-md border border-block/30 bg-block/[0.08] p-3 text-[13px] text-ink-100">
            The server has no management token configured, so the dashboard is disabled. Set{' '}
            <code className="font-mono text-[12px]">SENTINEL_API_TOKEN</code> and restart the gateway.
          </p>
        ) : (
          <>
            <label className="block text-[13px] text-ink-200" htmlFor="token">
              Access token
              <input
                id="token"
                type="password"
                autoComplete="off"
                spellCheck={false}
                className="field mt-1.5 h-9 font-mono"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
            </label>
            {message && (
              <p role="alert" className="text-[13px] text-block">
                {message}
              </p>
            )}
            <button type="submit" className="btn-primary btn-lg w-full" disabled={busy || !input.trim()}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <KeyRound className="h-4 w-4" aria-hidden />}
              Unlock dashboard
            </button>
          </>
        )}
        <p className="text-center text-[12.5px] text-ink-400">
          <a href="/" className="hover:text-ink-100">
            Back to home page
          </a>
        </p>
      </form>
    </main>
  );
}

export function SignOutButton({ compact = false }: { compact?: boolean }) {
  if (!getToken()) return null;
  return (
    <button
      className={`flex h-8 items-center gap-2.5 rounded-md hover:bg-white/[0.05] hover:text-ink-100 ${compact ? 'w-full justify-center' : 'w-full px-0'}`}
      title="Sign out"
      onClick={() => {
        clearToken();
        window.location.assign('/');
      }}
    >
      <KeyRound className="h-4 w-4 shrink-0" aria-hidden />
      <span className={compact ? 'sr-only' : ''}>Sign out</span>
    </button>
  );
}
