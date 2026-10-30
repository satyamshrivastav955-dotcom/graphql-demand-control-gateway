# API reference

Base URL: `http://localhost:8000` (the dashboard container proxies the same paths on `:8080`).

## `POST /graphql-proxy`

Analyse and, if permitted, forward a GraphQL operation.

```bash
curl -s http://localhost:8000/graphql-proxy -H 'content-type: application/json' \
  -d '{"query":"query Q($id: ID!) { user(id: $id) { name } }","variables":{"id":"1"},"operationName":"Q"}'
```

| Status | Meaning |
|---|---|
| `200` | Forwarded. Body is the upstream's response plus `extensions.security`. |
| `400` | Invalid body, syntax error, unknown/ambiguous operation (`decision: "ERROR"`). |
| `403` | BLOCK: hard limit violated or CRITICAL risk. Never forwarded. |
| `413` | Body larger than `limits.max_body_bytes`. |
| `429` | Rate limit or THROTTLE quota exceeded; see `Retry-After`. |
| `502` / `504` | Upstream failed / timed out (generic message, no internal detail). |
| `503` | No upstream configured in `proxy` mode. |

`extensions.security`:

```json
{
  "event_id": "…", "decision": "ALLOW", "enforced": "forwarded",
  "risk_tier": "SAFE", "score": 10.0, "rule_score": 10.0, "ml_score": 0.01,
  "explanations": [{"rule": "sensitive_fields", "feature": "sensitive_field_count", "value": 1,
                    "points": 10, "severity": "medium", "description": "…"}],
  "limit_violations": [], "latency_ms": 1.4
}
```

`enforced` is one of `forwarded`, `blocked`, `rate_limited`, `upstream_error`, `rejected`, `simulated`.
Every response carries `X-Sentinel-Decision`.

## `POST /api/analyze`

Dry run: same body, returns `{decision, risk_tier, score, rule_score, ml_score, features, explanations,
limit_violations, would_forward, latency_ms}`. Nothing is forwarded or stored.

## Gateway client keys (optional)

By default `/graphql-proxy` is anonymous. Set `SENTINEL_GATEWAY_KEYS` (comma-separated, each >= 16 characters) and it requires
`X-API-Key: <key>`; the management token is also accepted, which is how the dashboard playground keeps working. A missing or
wrong key gets `401` (or `429` after repeated failures from one IP, with a separate lockout from the dashboard login) and the
request is neither forwarded nor recorded. The key is never forwarded to the upstream (only `authorization` and `x-request-id`
are), so the upstream's own authentication is unaffected.

## Shadow mode, batching

With `SENTINEL_ENFORCEMENT=shadow` the gateway computes and records the real decision but forwards everything: the response
carries `extensions.security.shadow: true`, `enforced: "shadow"` and the headers `X-Sentinel-Decision` (what it *would*
have done) and `X-Sentinel-Shadow: true`. Body-size limits, parser budgets (`query_length`, `token_count`,
`parse_budget_exceeded`) and the per-IP rate limit still apply, because they protect the gateway itself.
Batched (array) requests are rejected with `400`; send one operation per request.

## Authentication

`/graphql-proxy`, `/api/health`, `/api/evaluation` and a minimal `/api/ready` are public. Every other `/api/*`
endpoint needs `Authorization: Bearer <SENTINEL_API_TOKEN>`:

| Status | Meaning |
|---|---|
| `401` | Missing or wrong token (`WWW-Authenticate: Bearer`) |
| `429` | IP locked out after repeated failures, or management-API rate limit exceeded (`Retry-After`) |
| `503` | No token configured on the server (fail closed) |

```bash
curl -H "Authorization: Bearer $SENTINEL_API_TOKEN" localhost:8000/api/metrics
```

## Dashboard endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness (public). |
| `GET /api/ready` | Public: `{status}` only. With a valid token: `{status, checks: {model, store, upstream}}` including an upstream probe; 503 if the event store is unavailable. |
| `GET /api/config` | Effective limits (and `client_key_required`), tiers, actions, throttle, mode, model info. No secrets (upstream host only). |
| `GET /api/events` | `limit, offset, decision, tier, q, sort=timestamp\|score, order=asc\|desc` → `{items, total, limit, offset}`. |
| `GET /api/events/export` | `format=csv\|json`, `limit` (<= 20000), `decision`, `tier`, `q` -> download. Queries are credential-redacted; CSV cells that could be spreadsheet formulas are neutralised. |
| `GET /api/events/{id}` | One event plus `client_timeline`. |
| `GET /api/metrics?minutes=60` | Counts, distributions, latency, load over time, top signals, recent suspicious events. |
| `GET /api/live` | Server-sent events, one `data:` line per new event. |
| `GET /api/evaluation` | The latest `ml/reports/evaluation.json`, or `{"available": false}` (public). |

| `GET /metrics` | Prometheus text format (token required): `sentinel_requests_total{decision,enforced}`, `sentinel_hard_limit_violations_total{limit}`, `sentinel_analysis_duration_seconds` and `sentinel_request_duration_seconds` histograms, `sentinel_alerts_total{result}`, `sentinel_info`, `sentinel_model_loaded`. Scrape the backend directly (the dashboard proxy does not forward it). |

The machine-readable spec is [`openapi.json`](openapi.json) (`python scripts/export_openapi.py`). Interactive `/docs` is served only when `app.debug` is true.

Prometheus example:

```yaml
scrape_configs:
  - job_name: sentinel
    metrics_path: /metrics
    authorization: {type: Bearer, credentials: <SENTINEL_API_TOKEN>}
    static_configs: [{targets: ['127.0.0.1:8000']}]
```
