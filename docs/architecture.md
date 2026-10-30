# Architecture

GraphQL Sentinel is a reverse proxy placed in front of one trusted GraphQL endpoint. Every operation is analysed
before it can reach the upstream.

```
                      ┌──────────────────────── Sentinel gateway (FastAPI) ────────────────────────┐
 Client ── POST ────► │ body limit → rate limit → parse + AST analysis → score → policy → enforce   │ ─► Upstream
 /graphql-proxy       │                          (features)     (rules+ML)  (tier→action)  │        │   GraphQL
                      │                                                                     ▼        │   (only if
                      │                                          audit event (SQLite) ◄──────┘        │   ALLOW /
 Dashboard ── GET ──► │ /api/events  /api/metrics  /api/live (SSE)  /api/config  /api/evaluation     │   within quota)
                      └──────────────────────────────────────────────────────────────────────────────┘
```

## Request flow (`backend/api/gateway.py`)

| Step | What happens | Outcome on failure |
|---|---|---|
| 1. Body | Read at most `limits.max_body_bytes`; must be a JSON object with a non-empty `query` string. | 413 / 400 |
| 2. Rate limit | Sliding window per client IP (`throttle.rate_limit` per `window_seconds`). | 429 + `Retry-After`, event recorded |
| 3. Analysis | Parse with `graphql-core` under a token budget, select the operation, resolve fragments, compute features (`backend/core/analysis/analyzer.py`). | 400 (syntax / ambiguous operation) or BLOCK (parse budget exceeded) |
| 4. Hard limits | Depth, aliases, cost, tokens, length, fragment cycles, optional introspection ban (`security_engine/limits.py`). | BLOCK (403) |
| 5. Score | Transparent rule score blended with an ML probability (`security_engine/scorer.py`, [scoring](scoring.md)). | ML failure → rules only |
| 6. Policy | Tier → action via `security.policy.tier_actions` (default: HIGH_RISK throttles, CRITICAL blocks). | unknown tier → BLOCK |
| 7. Enforce | BLOCK never reaches the upstream. THROTTLE operations share a small per-client quota (`throttle.risky_quota`). | 403 / 429 |
| 8. Forward | `httpx.AsyncClient` with connection pooling and a timeout; only an allow-list of headers is forwarded. | 502 / 503 / 504 with generic messages |
| 9. Audit | Event (decision, score, features, explanations, latency) written to SQLite; credentials in string literals are redacted; variables are never stored. | event failure never fails the request |

The upstream's own response body is returned unchanged except for an added `extensions.security` object.

## Operations features

* **Shadow mode** (`gateway.enforcement: shadow`): the pipeline runs unchanged, but BLOCK/THROTTLE decisions are recorded and
  forwarded (`enforced: shadow`) so a policy can be validated on live traffic before it is enforced.
* **Metrics** (`backend/core/runtime/metrics.py`): dependency-free Prometheus exposition at `/metrics`.
* **Alerts** (`backend/core/runtime/alerts.py`): bounded queue, per-minute cap, Slack-compatible webhook; overflow is counted,
  never retried, and a failing webhook cannot affect request handling.

## Management API protection

`backend/api/auth.py` guards every `/api/*` endpoint except health, evaluation and a minimal readiness: bearer token
(`SENTINEL_API_TOKEN`), constant-time comparison, per-IP lockout after repeated failures, per-IP rate limit, capped
live streams, fail-closed 503 when unconfigured. The dashboard prompts for the token and keeps it in `sessionStorage`.

## Modules

| Path | Responsibility |
|---|---|
| `backend/core/analysis/` | Fragment-aware feature extraction. Memoised per fragment, so a "fragment bomb" is analysed in linear time; cycles are detected, not followed. |
| `backend/core/security_engine/` | `rules.py` (attributable points), `scorer.py` (blend, model verification), `limits.py` (hard limits), `policy.py` (tier → action). |
| `backend/core/runtime/` | `limiter.py` (bounded sliding window), `events.py` (SQLite audit store with retention). |
| `backend/core/features/behavioral_store.py` | Per-client rate and repetition features (bounded LRU). |
| `backend/core/config.py` | Typed settings: YAML defaults overridden by `SENTINEL_*` environment variables. |
| `backend/api/` | `gateway.py` (the pipeline above), `routes.py` (HTTP surface). |
| `dashboard/` | React + TypeScript SPA: landing page and the `/app` dashboard. |
| `ml/` | Dataset generator, training, evaluation, reports (`python -m ml.run`). |
| `demo/upstream/` | A deliberately unprotected GraphQL server used as the demo/test target. |

## Design decisions

* **Rules first, ML second.** Rule points are individually explainable and always available. The classifier is a
  second opinion whose weight is chosen by how well it generalises to attack categories it never saw.
* **Hard limits are separate from scores.** A violated limit always blocks and can only raise severity.
* **Fail closed on policy, fail open on the ML term.** An unknown risk tier blocks; a missing or tampered model
  (checksum and feature-schema checked) falls back to rules.
* **No fake responses.** Without an upstream the gateway answers 503. `mode: simulation` exists for demos and
  labels every response `simulated`.
* **Bounded memory everywhere.** Limiter keys, behavioural history and stored events are all capped.
* **Client identity is the IP address**, never a header the client controls (`X-Client-ID` is only a label).
  `X-Forwarded-For` is honoured only when `gateway.trust_proxy_headers` is enabled.
