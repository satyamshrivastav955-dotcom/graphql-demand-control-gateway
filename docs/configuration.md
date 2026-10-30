# Configuration

Settings live in `backend/config/settings.yaml` and are validated at start-up (`backend/core/config.py`).
Any value can be overridden by an environment variable `SENTINEL_<SECTION>__<KEY>` (double underscore between
levels), and the most common ones have short aliases. See `.env.example`.

| Setting | Default | Notes |
|---|---|---|
| `api.token` / `SENTINEL_API_TOKEN` | none | **Required.** Bearer token for the management API and dashboard login (>= 16 chars). Without it those endpoints answer 503 |
| `api.auth_required` | true | `false` disables management-API auth (development only; logged as a warning) |
| `api.auth_failures`, `api.auth_window_seconds` | 10 / 300 | failed attempts per IP before lockout (429) |
| `api.rate_limit_per_minute`, `api.max_live_streams` | 120 / 5 | authenticated API rate limit per IP; concurrent live streams |
| `gateway.mode` / `SENTINEL_MODE` | `proxy` | `simulation` returns a labelled fake response; never use in production |
| `gateway.enforcement` / `SENTINEL_ENFORCEMENT` | `enforce` | `shadow` records real decisions but forwards everything (report-only rollout) |
| `alerts.webhook_url` / `SENTINEL_ALERT_WEBHOOK_URL` | none | Slack-compatible webhook for blocked operations; the URL is a secret and is never logged or exposed |
| `alerts.min_decision`, `alerts.include_query`, `alerts.max_per_minute` | BLOCK / false / 30 | which decisions alert, whether (redacted) query text is included, send cap |
| `gateway.client_keys` / `SENTINEL_GATEWAY_KEYS` | none | Comma-separated keys (>= 16 chars each). When set, `/graphql-proxy` requires `X-API-Key` (management token also accepted) |
| `gateway.upstream_url` / `SENTINEL_UPSTREAM_URL` | none | Required in `proxy` mode; without it allowed operations get 503 |
| `gateway.upstream_timeout_seconds` | 10 | |
| `gateway.forward_headers` | `authorization`, `x-request-id` | Allow-list of client headers sent upstream |
| `gateway.trust_proxy_headers` | false | Read client IP from `X-Forwarded-For` (only behind a trusted proxy) |
| `limits.max_body_bytes` | 100000 | 413 above this |
| `limits.max_query_length` | 20000 | characters |
| `limits.max_depth` | 15 | |
| `limits.max_aliases` | 50 | |
| `limits.max_complexity` | 20000 | cost model, see [scoring](scoring.md) |
| `limits.max_tokens` | 5000 | |
| `security.introspection` / `SENTINEL_INTROSPECTION` | `flag` | `allow`, `flag` (scored +45), `block` (hard limit) |
| `security.policy.risk_tier_thresholds` | 20 / 40 / 65 / 85 | upper bounds of SAFE / LOW / MEDIUM / HIGH |
| `security.policy.tier_actions` | HIGH → THROTTLE, CRITICAL → BLOCK | each tier maps to ALLOW, THROTTLE or BLOCK |
| `security.policy.ml_weight` | unset | unset = weight recorded with the model; `0` disables the ML term |
| `throttle.rate_limit`, `window_seconds` | 100 per 60 s | per client IP, all traffic |
| `throttle.risky_quota` | 5 | THROTTLE-tier operations per client per window |
| `throttle.max_tracked_clients` | 10000 | memory bound |
| `storage.db_path` / `SENTINEL_DB_PATH` | `backend/storage/sentinel.db` | `/data/sentinel.db` in Docker (named volume) |
| `storage.max_events` | 50000 | oldest events are pruned |
| `cors.allow_origins` / `SENTINEL_CORS_ORIGINS` | localhost dev ports | comma-separated in the env var |
| `app.debug` / `SENTINEL_DEBUG` | false | enables `/docs` and verbose logging |

The dashboard's Policies page shows the effective values from `GET /api/config`. Configuration is read at
start-up; there is deliberately no runtime edit endpoint, so no API call can change policy.
