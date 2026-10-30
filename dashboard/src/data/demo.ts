import raw from './demoSamples.json';
import type { Decision, Severity, Tier } from '../api/types';

export interface DemoExplanation {
  rule: string;
  feature: string;
  value: number | string;
  points: number;
  severity: Severity;
  description: string;
}

export interface DemoSample {
  id: string;
  title: string;
  blurb: string;
  query: string;
  decision: Decision;
  risk_tier: Tier;
  score: number;
  rule_score: number;
  ml_score: number | null;
  limit_violations: string[];
  explanations: DemoExplanation[];
  features: Record<string, number>;
}

export interface DemoData {
  recorded_at: string;
  engine_version: string;
  model: string | null;
  ml_weight: number;
  samples: DemoSample[];
}

/** Real engine output recorded by `scripts/export_demo_samples.py`. */
export const DEMO = raw as unknown as DemoData;

/** Default hard limits shipped in backend/config/settings.yaml (shown as reference marks in the console). */
export const DEFAULT_LIMITS = { depth: 15, aliases: 50, cost: 20000 };

/** Default tier upper bounds (SAFE / LOW / MEDIUM / HIGH; above is CRITICAL). */
export const DEFAULT_TIERS = [20, 40, 65, 85];

export const ENFORCEMENT: Record<'ALLOW' | 'THROTTLE' | 'BLOCK', { status: string; text: string }> = {
  ALLOW: { status: '200', text: 'Forwarded to your upstream; its response comes back unchanged.' },
  THROTTLE: {
    status: '200 / 429',
    text: 'Forwarded while the client is inside its high-risk quota (5 per minute by default); past that it gets 429 with Retry-After.',
  },
  BLOCK: { status: '403', text: 'Answered with 403. The operation never reaches your upstream.' },
};
