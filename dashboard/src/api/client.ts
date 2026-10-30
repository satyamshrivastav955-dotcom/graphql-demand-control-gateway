import type {
  AnalyzeResult,
  Decision,
  EventDetailData,
  EventsPage,
  Evaluation,
  GatewayConfig,
  GatewayResponse,
  Metrics,
  Ready,
} from './types';
import { authHeaders, clearToken, getToken, signalAuthRequired } from './auth';

const apiKeyHeader = (): Record<string, string> => {
  const t = getToken();
  return t ? { 'X-API-Key': t } : {};
};

/** Same-origin by default; override with VITE_API_URL for a remote gateway. */
export const API_BASE: string = import.meta.env.VITE_API_URL ?? '';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return String(body.detail[0].msg);
    if (body?.errors?.[0]?.message) return String(body.errors[0].message);
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...(init?.headers as Record<string, string> | undefined) },
    });
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') throw e;
    throw new ApiError('Cannot reach the Sentinel gateway.', 0);
  }
  if (res.status === 401) {
    // Only management endpoints answer 401: the token is missing, wrong or expired.
    clearToken();
    signalAuthRequired();
  }
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status);
  return (await res.json()) as T;
}

export interface QueryBody {
  query: string;
  variables?: Record<string, unknown>;
  operationName?: string;
}

export interface EventParams {
  limit?: number;
  offset?: number;
  decision?: string;
  tier?: string;
  q?: string;
  sort?: 'timestamp' | 'score';
  order?: 'asc' | 'desc';
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export interface ProxyOutcome {
  status: number;
  decisionHeader: Decision | null;
  body: GatewayResponse;
}

export const api = {
  ready: (signal?: AbortSignal) => request<Ready>('/api/ready', { signal }),
  config: (signal?: AbortSignal) => request<GatewayConfig>('/api/config', { signal }),
  metrics: (minutes: number, signal?: AbortSignal) =>
    request<Metrics>(`/api/metrics${qs({ minutes })}`, { signal }),
  events: (p: EventParams, signal?: AbortSignal) =>
    request<EventsPage>(`/api/events${qs({ ...p })}`, { signal }),
  event: (id: string, signal?: AbortSignal) =>
    request<EventDetailData>(`/api/events/${encodeURIComponent(id)}`, { signal }),
  evaluation: (signal?: AbortSignal) => request<Evaluation>('/api/evaluation', { signal }),
  analyze: (body: QueryBody, signal?: AbortSignal) =>
    request<AnalyzeResult>('/api/analyze', { ...json(body), signal }),

  /** Sends the operation through the enforcing gateway. Non-2xx decisions are returned, not thrown. */
  async proxy(body: QueryBody, clientId = 'dashboard-playground'): Promise<ProxyOutcome> {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/graphql-proxy`, {
        method: 'POST',
        // The management token doubles as an API key when the gateway requires client keys.
        headers: { 'Content-Type': 'application/json', 'X-Client-ID': clientId, ...apiKeyHeader() },
        body: JSON.stringify(body),
      });
    } catch {
      throw new ApiError('Cannot reach the Sentinel gateway.', 0);
    }
    let parsed: GatewayResponse;
    try {
      parsed = (await res.json()) as GatewayResponse;
    } catch {
      throw new ApiError(`Gateway returned a non-JSON response (${res.status}).`, res.status);
    }
    return {
      status: res.status,
      decisionHeader: (res.headers?.get?.('X-Sentinel-Decision') as Decision | null) ?? null,
      body: parsed,
    };
  },
};

export const liveUrl = () => `${API_BASE}/api/live`;

export type AccessState = 'ok' | 'unauthorized' | 'unconfigured' | 'locked' | 'unreachable';

/** Checks whether the management API accepts the given token (or the stored one / none). */
export async function probeAccess(token?: string): Promise<AccessState> {
  try {
    const res = await fetch(`${API_BASE}/api/config`, {
      headers: token ? { Authorization: `Bearer ${token}` } : authHeaders(),
    });
    if (res.ok) return 'ok';
    if (res.status === 401) return 'unauthorized';
    if (res.status === 503) return 'unconfigured';
    if (res.status === 429) return 'locked';
    return 'unreachable';
  } catch {
    return 'unreachable';
  }
}
