import { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import type {
  AnalyzeResult,
  Evaluation,
  GatewayConfig,
  Metrics,
  Ready,
  SentinelEvent,
} from '../api/types';

type Handler = (url: URL, init?: RequestInit) => { status?: number; body: unknown; headers?: Record<string, string> } | Promise<{ status?: number; body: unknown; headers?: Record<string, string> }>;

/** Installs a fetch mock. Keys are pathnames (exact). Unknown paths return 404. Returns the mock for assertions. */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    const r = routes[url.pathname] ?? (url.pathname === '/api/config' ? CONFIG : undefined); // the access gate probes /api/config
    if (r === undefined) return makeResponse(404, { detail: 'not found' });
    const out = typeof r === 'function' ? await (r as Handler)(url, init) : { body: r };
    return makeResponse(out.status ?? 200, out.body, out.headers);
  });
  (global as unknown as { fetch: unknown }).fetch = fn;
  return fn;
}

export function makeResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k: string) => headers[k] ?? headers[k.toLowerCase()] ?? null },
    json: async () => body,
  } as unknown as Response;
}

export function networkDown() {
  (global as unknown as { fetch: unknown }).fetch = vi.fn(async () => {
    throw new TypeError('Failed to fetch');
  });
}

export function renderAt(path: string, ui?: ReactElement) {
  return render(<MemoryRouter initialEntries={[path]}>{ui ?? <AppRoutes />}</MemoryRouter>);
}

export const READY: Ready = { status: 'ready', checks: { model: true, store: true, upstream: 'ok' } };

export const EVENT: SentinelEvent = {
  id: 'evt_1',
  timestamp: '2026-01-02T03:04:05Z',
  client_id: 'client-a',
  ip: '10.0.0.1',
  operation_name: 'Deep',
  operation_type: 'query',
  query: 'query Deep { a { b { c { d } } } }',
  decision: 'BLOCK',
  enforced: 'blocked',
  risk_tier: 'CRITICAL',
  score: 91.5,
  rule_score: 88,
  ml_score: 0.97,
  features: { max_depth: 12, alias_count: 0 },
  explanations: [{ rule: 'excessive_depth', feature: 'max_depth', value: 12, points: 60, severity: 'high', description: 'Nesting depth 12 exceeds the limit.' }],
  limit_violations: ['max_depth exceeded (10)'],
  upstream_status: null,
  latency_ms: 0.8,
  total_latency_ms: 0.9,
};

export const EVENT_ALLOW: SentinelEvent = {
  ...EVENT,
  id: 'evt_2',
  decision: 'ALLOW',
  enforced: 'forwarded',
  risk_tier: 'SAFE',
  score: 3,
  rule_score: 2,
  ml_score: 0.01,
  query: 'query Ok { me { name } }',
  explanations: [],
  limit_violations: [],
  upstream_status: 200,
};

export const METRICS: Metrics = {
  total_queries: 120,
  allowed_count: 100,
  throttled_count: 12,
  blocked_count: 8,
  error_count: 0,
  avg_score: 14.2,
  avg_latency_ms: 0.8,
  p95_latency_ms: 1.9,
  block_rate: 8 / 120,
  active_clients: 5,
  tier_distribution: { SAFE: 90, LOW_RISK: 10, MEDIUM_RISK: 8, HIGH_RISK: 4, CRITICAL: 8 },
  decision_distribution: { ALLOW: 100, THROTTLE: 12, BLOCK: 8, ERROR: 0 },
  load_over_time: [
    { time: '10:00', total: 10, allowed: 8, throttled: 1, blocked: 1 },
    { time: '10:01', total: 20, allowed: 18, throttled: 1, blocked: 1 },
  ],
  top_signals: [{ rule: 'excessive_depth', count: 7 }],
  recent_suspicious: [EVENT],
};

export const CONFIG: GatewayConfig = {
  version: '1.2.3',
  mode: 'proxy',
  upstream_configured: true,
  upstream_host: 'upstream.internal:4000',
  limits: { max_body_bytes: 65536, max_query_length: 10000, max_depth: 10, max_aliases: 30, max_complexity: 1000, max_tokens: 5000 },
  introspection: 'flag',
  tiers: { safe: 20, low_risk: 40, medium_risk: 65, high_risk: 85 },
  tier_actions: { SAFE: 'ALLOW', LOW_RISK: 'ALLOW', MEDIUM_RISK: 'ALLOW', HIGH_RISK: 'THROTTLE', CRITICAL: 'BLOCK' },
  throttle: { rate_limit: 100, window_seconds: 60 },
  model: { loaded: true, name: 'random_forest', trained_at: '2026-01-01T00:00:00Z', n_features: 12 },
};

export const ANALYZE: AnalyzeResult = {
  decision: 'THROTTLE',
  risk_tier: 'HIGH_RISK',
  score: 72.4,
  rule_score: 70,
  ml_score: 0.81,
  features: { max_depth: 9, alias_count: 0 },
  explanations: [{ rule: 'excessive_depth', feature: 'max_depth', value: 9, points: 45, severity: 'medium', description: 'Depth 9 is above the norm.' }],
  limit_violations: [],
  would_forward: true,
  latency_ms: 0.6,
};

export const EVAL_AVAILABLE: Evaluation = {
  available: true,
  generated_at: '2026-02-03T04:05:06Z',
  seed: 1234,
  dataset: { version: 'v7', n_train: 800, n_val: 100, n_test: 200, attack_ratio_test: 0.5, categories: ['benign', 'deep'] },
  methods: [
    { name: 'Rules', description: 'Rule engine only', precision: 0.9, recall: 0.8, f1: 0.847, fpr: 0.05, roc_auc: 0.9, pr_auc: 0.88, confusion: { tp: 80, fp: 5, tn: 95, fn: 20 }, latency_us_p50: 50, latency_us_p95: 90 },
    { name: 'Combined', description: 'Rules + ML', precision: 0.95, recall: 0.9, f1: 0.924, fpr: 0.03, roc_auc: null, pr_auc: null, confusion: { tp: 90, fp: 3, tn: 97, fn: 10 }, latency_us_p50: 70, latency_us_p95: 120 },
  ],
  per_category: [
    { category: 'benign_simple', n: 100, is_attack: false, detection_rate: { Rules: 0.05, Combined: 0.03 } },
    { category: 'deep_nesting', n: 50, is_attack: true, detection_rate: { Rules: 0.9, Combined: 0.96 } },
  ],
  real_world_benign: { source: 'NL2GQL', n: 500, false_positive_rate: { Rules: 0.02, Combined: 0.01 } },
  gateway_overhead: { p50_ms: 1.5, p95_ms: 3.5, requests_per_second: 700, n: 1000 },
  limitations: ['Synthetic attack traffic only.'],
  environment: { python: '3.13.0', platform: 'linux', cpu: 'x86' },
};
