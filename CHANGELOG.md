# Changelog

## 1.0.0 (unreleased)

First complete version. Replaces the earlier prototype, whose proxy returned a mock response and whose ML scores
did not influence decisions.

### Gateway
* Real forwarding to a configured upstream (`httpx`, pooled, timeouts, generic upstream errors). BLOCK never
  reaches the upstream; no fake success without an upstream (explicit, labelled `simulation` mode only).
* Enforced THROTTLE: per-client sliding-window limits (bounded memory) with `429` and `Retry-After`.
* Hard limits for body size, query length, tokens, depth, aliases and cost; configurable introspection policy.
* Request analysis is fragment-aware (depth hidden behind fragments, fragment cycles, fragment bombs in linear
  time) and no longer treats `__typename` as introspection.
* SQLite audit store with retention, credential redaction, and no variable storage.
* Typed settings with `SENTINEL_*` environment overrides; production-safe defaults (debug off, CORS without
  credentials).

### Scoring and ML
* Attributable rule score + checksummed scikit-learn model, blended with a documented, tested formula.
* New dataset generator (21 categories, overlapping ranges, skeleton-level de-duplication), reproducible
  evaluation with baselines, per-category results, false-positive check on real queries, leave-one-category-out
  generalisation, an independent confirmation set and gateway overhead (`python -m ml.run`).
* Removed the autoencoder/ensemble/LSTM/GNN placeholders and the hard-coded accuracy numbers.

### Operations
* Shadow (report-only) enforcement mode, Prometheus `/metrics`, Slack-compatible webhook alerts, CSV/JSON events export,
  explicit rejection of batched requests, startup warm-up, load-test script with recorded baseline (`docs/performance.md`),
  exported OpenAPI spec.

* The gateway serves the built landing page and dashboard itself (`/` and `/app`), so `python scripts/dev.py` shows the product at
  http://127.0.0.1:8000; `dev.py` builds the dashboard on first run and whenever its sources change.

### Security
* Management API (`/api/*` except health, evaluation, minimal readiness) requires a bearer token: constant-time
  comparison, per-IP lockout, rate limiting, live-stream cap, fail-closed when unconfigured. Public readiness no
  longer probes the upstream. Security headers, no-store, docs disabled by default. nginx CSP and rate limits.
* Upgraded graphql-core to 3.2.12 (two CVEs) and react-router-dom to 7.18.5; removed the Google Fonts request.
* Optional API keys for the enforcing endpoint (`SENTINEL_GATEWAY_KEYS`, `X-API-Key`): constant-time check, separate
  lockout, rejected before the body is read, never recorded or forwarded.
* MIT licence, third-party notice, deployment guide with a pre-flight review.

### Dashboard
* New landing page and dashboard (overview, request analysis, events, policies, evaluation) wired to the API.

### Packaging
* Root `docker-compose.yml` (gateway, nginx-served dashboard, demo upstream), non-root read-only containers,
  health checks, CI for lint, tests with coverage, ML pipeline smoke test, dashboard build and Docker build.
