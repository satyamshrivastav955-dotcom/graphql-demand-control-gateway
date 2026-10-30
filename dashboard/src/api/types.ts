export type Decision = 'ALLOW' | 'THROTTLE' | 'BLOCK' | 'ERROR';
export type Tier = 'SAFE' | 'LOW_RISK' | 'MEDIUM_RISK' | 'HIGH_RISK' | 'CRITICAL';
export type Severity = 'info' | 'low' | 'medium' | 'high';
export type Enforced =
  | 'forwarded'
  | 'blocked'
  | 'rate_limited'
  | 'upstream_error'
  | 'rejected'
  | 'simulated'
  /** Shadow (report-only) mode: the decision was recorded but the operation was forwarded regardless. */
  | 'shadow';

export type Enforcement = 'enforce' | 'shadow';

export const TIERS: Tier[] = ['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK', 'CRITICAL'];
export const DECISIONS: Decision[] = ['ALLOW', 'THROTTLE', 'BLOCK', 'ERROR'];

export interface Explanation {
  rule: string;
  feature: string;
  value: number | string;
  points: number;
  severity: Severity;
  description: string;
}

export interface SecurityExtension {
  event_id?: string;
  decision: Decision;
  enforced?: Enforced;
  risk_tier?: Tier;
  score?: number;
  rule_score?: number;
  ml_score?: number | null;
  explanations?: Explanation[];
  limit_violations?: string[];
  latency_ms?: number;
  simulated?: boolean;
  /** True in shadow mode: `decision` is what the gateway *would* have done. */
  shadow?: boolean;
}

export interface GatewayResponse {
  data?: unknown;
  errors?: { message: string }[];
  extensions?: { security?: SecurityExtension };
}

export interface AnalyzeResult {
  decision: Decision;
  risk_tier: Tier;
  score: number;
  rule_score: number;
  ml_score: number | null;
  features: Record<string, number>;
  explanations: Explanation[];
  limit_violations: string[];
  would_forward: boolean;
  latency_ms: number;
}

export interface SentinelEvent {
  id: string;
  timestamp: string;
  client_id: string;
  ip: string;
  operation_name: string | null;
  operation_type: 'query' | 'mutation' | 'subscription' | null;
  query: string;
  decision: Decision;
  enforced: Enforced;
  risk_tier: Tier;
  score: number;
  rule_score: number;
  ml_score: number | null;
  features: Record<string, number>;
  explanations: Explanation[];
  limit_violations: string[];
  upstream_status: number | null;
  latency_ms: number;
  total_latency_ms: number;
}

export interface EventDetailData extends SentinelEvent {
  client_timeline: { timestamp: string; score: number; decision: Decision }[];
}

export interface EventsPage {
  items: SentinelEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface Metrics {
  total_queries: number;
  allowed_count: number;
  throttled_count: number;
  blocked_count: number;
  error_count: number;
  avg_score: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  block_rate: number;
  active_clients: number;
  tier_distribution: Record<Tier, number>;
  decision_distribution: Record<Decision, number>;
  load_over_time: { time: string; total: number; allowed: number; throttled: number; blocked: number }[];
  top_signals: { rule: string; count: number }[];
  recent_suspicious: SentinelEvent[];
}

export interface Ready {
  status: 'ready' | 'degraded';
  /** Only present for authenticated callers; the public response is just `status`. */
  checks?: {
    model: boolean;
    store: boolean;
    upstream: 'ok' | 'unreachable' | 'not_configured' | 'simulation';
  };
}

export interface GatewayConfig {
  version: string;
  mode: 'proxy' | 'simulation';
  /** 'shadow' = decisions are recorded but not enforced. Absent on older gateways. */
  enforcement?: Enforcement;
  upstream_configured: boolean;
  /** True when /graphql-proxy requires an X-API-Key. */
  client_key_required?: boolean;
  upstream_host: string | null;
  limits: {
    max_body_bytes: number;
    max_query_length: number;
    max_depth: number;
    max_aliases: number;
    max_complexity: number;
    max_tokens: number;
  };
  introspection: 'allow' | 'flag' | 'block';
  tiers: { safe: number; low_risk: number; medium_risk: number; high_risk: number };
  tier_actions: Record<Tier, Decision>;
  throttle: { rate_limit: number; window_seconds: number };
  model: { loaded: boolean; name: string | null; trained_at: string | null; n_features: number | null };
}

export interface EvalMethod {
  name: string;
  description: string;
  precision: number;
  recall: number;
  f1: number;
  fpr: number;
  roc_auc: number | null;
  pr_auc: number | null;
  confusion: { tp: number; fp: number; tn: number; fn: number };
  latency_us_p50: number;
  latency_us_p95: number;
}

export type Evaluation =
  | { available: false }
  | {
      available: true;
      generated_at: string;
      seed: number;
      dataset: {
        version: string;
        n_train: number;
        n_val: number;
        n_test: number;
        attack_ratio_test: number;
        categories: string[];
      };
      methods: EvalMethod[];
      per_category: {
        category: string;
        n: number;
        is_attack: boolean;
        detection_rate: Record<string, number>;
      }[];
      real_world_benign: {
        source: string;
        n: number;
        false_positive_rate: Record<string, number>;
      } | null;
      gateway_overhead: { p50_ms: number; p95_ms: number; requests_per_second: number; n: number } | null;
      /** Leave-one-attack-category-out results: recall on a category the model never saw in training. */
      generalization?: {
        description: string;
        folds: {
          held_out_category: string;
          n: number;
          ml_recall: number;
          rules_recall: number;
          combined_recall: number;
          ml_fpr: number;
          combined_fpr: number;
        }[];
      };
      limitations: string[];
      environment: { python: string; platform: string; cpu: string };
    };
