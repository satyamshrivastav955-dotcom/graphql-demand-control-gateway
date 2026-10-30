# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Every allowed request returns `503 Upstream GraphQL endpoint is not configured` | `proxy` mode with no upstream. Set `SENTINEL_UPSTREAM_URL`, or `SENTINEL_MODE=simulation` for a labelled demo. |
| `502`/`504` for allowed requests | The upstream is down, slow (> `gateway.upstream_timeout_seconds`) or returned non-JSON. Check `GET /api/ready`. |
| Dashboard shows a token prompt / `401` | Enter `SENTINEL_API_TOKEN` (printed by `scripts/dev.py`, or from your `.env`). The token is kept per browser tab. |
| Dashboard says no management token is configured / `503` | Set `SENTINEL_API_TOKEN` (>= 16 chars) and restart the gateway. |
| `429` on `/api/*` after wrong tokens | Per-IP lockout (`api.auth_failures` in `api.auth_window_seconds`); wait for `Retry-After`. |
| `docker compose up` fails with "Set SENTINEL_API_TOKEN" | Create `.env` from `.env.example` and set the token. |
| Everything is `429` | Per-IP limit reached (`throttle.rate_limit`). Behind a proxy, enable `SENTINEL_TRUST_PROXY_HEADERS` so clients are not all one IP. |
| `GET /api/ready` shows `model: false` | The scorer fell back to rules only. Causes: missing `backend/core/models/risk_model.*`, checksum or feature-schema mismatch, scikit-learn version differing from `backend/requirements.txt`. Retrain with `python -m ml.run`. |
| Dashboard shows "gateway unreachable" | The API is not on the same origin. In development the dashboard proxies to `localhost:8000`; in production set `VITE_API_URL` at build time or serve both behind one host (see `docker/nginx.conf`). |
| CORS errors in the browser | Add the dashboard origin to `SENTINEL_CORS_ORIGINS`. |
| Live stream stalls behind a proxy | Disable response buffering for `/api/live` (nginx: `proxy_buffering off`). |
| A legitimate query is blocked | Inspect the event in the dashboard: `limit_violations` and the explanations show which rule fired. Raise the relevant `limits.*` value or adjust `security.policy`. |
| `python -m ml.run` is slow | Dataset analysis dominates (a few minutes for 1000 operations per category). The dataset is cached in `ml/data/generated/`; use `--per-category 100` for a quick run. |
| `ModuleNotFoundError: backend` | Run commands from the repository root (`python -m pytest`, `python -m ml.run`, `uvicorn backend.main:app`). |
