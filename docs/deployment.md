# Deployment

**Status: not deployed, and not yet ready for an unattended public deployment.** This page records what was
reviewed, what is verified, what is still open, and the exact steps to deploy later. Nothing here has been run
against a real host, a real domain or Docker (see [Verification status](#verification-status)).

## Security review summary

| Endpoint | Data / effect | Exposure | Control |
|---|---|---|---|
| `POST /graphql-proxy` | Triggers analysis and an upstream call | Anonymous by default; **set `SENTINEL_GATEWAY_KEYS` to require `X-API-Key`** | Optional client keys (separate per-IP lockout), body limit, hard limits, per-IP rate limit, THROTTLE quota, nginx rate limit; BLOCK never forwards |
| `GET /api/events`, `/api/events/{id}` | Query text, client IPs, decisions | **Sensitive** | Bearer token, per-IP failed-auth lockout, per-IP rate limit |
| `GET /api/metrics`, `/api/live` | Traffic statistics, live events | **Sensitive** | Same; live streams capped (5) |
| `GET /api/config` | Limits, thresholds, upstream **host** | Sensitive (helps tune evasion) | Same |
| `POST /api/analyze` | CPU use; shows exact scores (probing oracle) | Abusable | Same |
| `GET /api/ready` | Reachability | Public returns `{"status"}` only; no upstream probe | Details and the upstream probe need the token |
| `GET /api/health`, `GET /api/evaluation` | Liveness; static benchmark report | Public, harmless | none needed |
| *(none)* | Policy modification | There is **no endpoint that changes policy**; configuration is file/env only | n/a |

Controls implemented and covered by automated tests (`backend/tests/test_security.py`, `dashboard/src/test/auth.test.tsx`):
bearer-token auth with constant-time comparison; fail-closed 503 when no token is configured; lockout after repeated
failures (also blocks the right token from that IP for the window); per-IP management-API rate limit; live-stream cap;
no unauthenticated upstream probing; no credentials, queries or upstream details in unauthenticated responses; security
headers and `Cache-Control: no-store` on `/api/*`; interactive docs disabled; CORS limited to configured origins without
credentials; dashboard keeps the token in `sessionStorage` only and returns to the prompt on any 401.
Defence in depth in `docker/nginx.conf` (not exercised here): CSP, rate limiting, body limit, no third-party assets.

## Must be resolved or accepted before a public demo

1. **Visitors' queries and IPs are stored** and visible to anyone holding the token. A public demo needs a privacy
   notice and a retention decision (`storage.max_events`), and the token must never be shared with visitors. Because the
   dashboard is token-gated, public visitors only see the landing page and can use `/graphql-proxy` directly; show the
   dashboard through screenshots or a private session.
2. **One shared, full-access token.** No roles, no per-user audit, rotation needs a restart. Acceptable for a single
   operator; not for a team.
3. **No TLS inside the stack.** Use the Caddy overlay (below) or another TLS terminator. Never publish port 8000/8080
   directly on the internet.
4. **The enforcing endpoint is anonymous unless you set client keys.** With `SENTINEL_GATEWAY_KEYS` unset anyone can send
   operations; the limits protect the upstream but cost CPU and disk (one SQLite row per request, pruned at
   `storage.max_events`). For a public demo that should not be open, set one or more keys and give them only to intended
   users (keys are shared secrets, not per-user identities). Keyless requests are rejected before the body is read and are
   not recorded. If the demo must stay open, expect scanners and watch disk and CPU.
5. **Rate-limit state is per process and per IP.** Visitors behind one NAT share a quota; a second replica doubles the
   limits. Run one backend replica.
6. **`trust_proxy_headers` is on in Compose.** It is only safe because nginx overwrites `X-Forwarded-For` and the backend
   port is bound to `127.0.0.1`. Do not publish the backend port on a public interface.
7. **Dependency audit.** The dashboard was migrated from Create React App to Vite; `npm audit` (all dependencies, not
   only production) now reports 0 vulnerabilities, and `pip-audit` on the backend requirements reports none. Re-run both
   before each release: advisories appear over time and CI runs `npm audit` on every build.
8. **Unverified:** Docker images, the full Compose stack, nginx and Caddy configuration, behaviour behind a real proxy
   (see below). Verify these before exposing anything.
9. **Lockout is per IP.** Ten wrong tokens lock an address out of the management API for 5 minutes (verified live), so a
   hostile user behind the same NAT/IP as the operator can lock the operator out temporarily. The anonymous gateway
   endpoint is unaffected. Restart the gateway or wait to clear it.
10. **Demo upstream is deliberately unprotected.** It must stay on the private Compose network (it does) and hold no real data.

## Verification status

| Item | Status |
|---|---|
| Backend unit/integration/security tests | Executed, passing |
| Dashboard tests, type-check, production build | Executed, passing |
| Gateway + demo upstream + dashboard dev server in a real browser | Executed (see README screenshots) |
| `docker compose config` | Executed (syntax only) |
| Docker image builds, `docker compose up`, container health checks | **Not executed** (no Docker daemon available) |
| `docker/nginx.conf` (CSP, `limit_req`, proxying incl. SSE) | **Static review only**; production bundle checked in a browser through a stand-in server (see below) |
| Caddy overlay, TLS, real-IP handling | **Static review only** |
| CI Docker job | **Never run** |

## Recommended rollout for a real API

1. **Shadow first.** Deploy with `SENTINEL_ENFORCEMENT=shadow`. Everything is forwarded; the dashboard and `/metrics` show what
   *would* have been blocked or throttled. Review false positives for a few days against real traffic.
2. **Tune** `limits.*`, `security.policy.*` and `security.introspection` from what you saw (see the Events page and the
   explanations on each event).
3. **Enforce** by removing the variable. Add `SENTINEL_ALERT_WEBHOOK_URL` for block notifications and scrape `/metrics`
   with Prometheus (`docs/api.md`).
4. If your upstream cannot survive a high-risk operation, set `security.policy.tier_actions.HIGH_RISK: BLOCK`; THROTTLE still
   forwards a small quota (see [performance](performance.md) for what happens otherwise).

## Local Docker verification (do this first)

```bash
cp .env.example .env
# edit .env: set SENTINEL_API_TOKEN to a random value (>= 16 chars):
python -c "import secrets; print(secrets.token_urlsafe(32))"

docker compose config -q                 # syntax check
docker compose build                     # builds backend, dashboard (npm ci + build), demo upstream
docker compose up -d --wait              # waits for health checks
docker compose ps                        # all three services should be healthy

curl -i localhost:8080/api/health                                    # 200
curl -i localhost:8080/api/events                                    # 401 (no token)
curl -i -H "Authorization: Bearer $SENTINEL_API_TOKEN" localhost:8080/api/config   # 200
curl -s localhost:8080/graphql-proxy -H 'content-type: application/json' \
  -d '{"query":"{ users(first: 2) { name } }"}'                      # real upstream data, decision ALLOW
SENTINEL_API_TOKEN=... python scripts/e2e_check.py --base http://127.0.0.1:8080   # 14+3 checks
docker compose logs backend | tail                                   # no tracebacks
docker compose exec backend id                                       # uid=10001, not root
docker compose down -v
```

Open <http://localhost:8080/app>, enter the token, and confirm the page renders with no CSP errors in the browser
console. If a service is unhealthy: `docker compose logs <service>`. Likely culprits: a read-only filesystem write
(add a `tmpfs`), or the nginx config (`docker compose exec dashboard nginx -t`).

## Future public deployment (single Linux VPS)

Prerequisites: a VPS with Docker and Compose v2, a DNS `A` record for your domain pointing at it, ports 80/443 open.
Costs: the VPS only (any small instance works); Caddy obtains a free Let's Encrypt certificate. I have not created any
resources.

```bash
git clone <repo> && cd GraphQL-Sentinel
cp .env.example .env
# .env: SENTINEL_API_TOKEN=<random>, SENTINEL_DOMAIN=demo.example.com,
#       SENTINEL_CORS_ORIGINS=https://demo.example.com, SENTINEL_TRUST_PROXY_HEADERS=true
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build --wait
curl -i https://demo.example.com/api/health          # 200 over TLS
curl -i https://demo.example.com/api/events          # 401
SENTINEL_API_TOKEN=... python scripts/e2e_check.py --base https://demo.example.com
```

Operations: back up the `sentinel-data` volume (SQLite); rotate the token by editing `.env` and
`docker compose up -d`; update with `git pull && docker compose ... up -d --build`; keep the firewall to 22/80/443.
To protect a real API instead of the demo upstream, set `SENTINEL_UPSTREAM_URL`, remove the `upstream` service and
make the real upstream reachable only from the gateway (private network or allow-list).
