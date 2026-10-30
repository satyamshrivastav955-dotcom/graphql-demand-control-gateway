# Product readiness: where this stands and what a real v1 needs

**Current status: a verified engineering project and public-demo candidate, not an industry-ready product.**
The gateway, scoring, evaluation, security controls and dashboard are implemented and tested. The gaps below are what
separate it from something a company would put in front of its production API.

## What is solid today

* Enforcing gateway with real upstream forwarding, hard limits, throttling, audit trail, fail-closed behaviour
  (126 backend tests, 97% coverage, live end-to-end checks, a recorded load-test baseline in [performance](performance.md)).
* Explainable scoring with a documented blend, reproducible evaluation, honest limitations.
* Token-protected management API, optional client keys, security headers, dependency audit clean for the backend.
* Operations basics: shadow (report-only) rollout mode, Prometheus `/metrics`, webhook alerts, events export, OpenAPI spec.

## Blockers for production use (must fix)

| # | Gap | Why it matters | Effort |
|---|---|---|---|
| 1 | **Docker/Compose/nginx/Caddy never executed** | Deployment artefacts are unverified; CI Docker job has never run | Hours: run the steps in `docs/deployment.md`, fix what breaks, get CI green |
| 2 | **No validation on real traffic** | All detection numbers are on synthetic data from one schema; real APIs differ. Thresholds may over/under-block | Weeks: shadow mode on a real API, label a sample, tune |
| 3 | **Single process, in-memory limiter state** | Cannot scale horizontally or survive restarts without losing rate-limit state | Days: Redis-backed limiter/behaviour store, or sticky routing |
| 4 | **One shared admin token, no roles/SSO** | No per-user audit, no least privilege, rotation needs restart | Days: OIDC login, roles (viewer/operator), per-key tokens |
| 5 | **Not schema-aware** | Cost uses argument heuristics (`first`, `limit`), not the real schema's list sizes and field costs | Days-weeks: load SDL/introspection, per-field cost directives |
| 6 | **Soak/chaos testing not done** | A single-process load baseline exists (~160-180 req/s, zero errors, [performance](performance.md)); no multi-hour soak, slow-upstream or failure drills, no Linux/production-host numbers | Days |
| 7 | **Tracing / SIEM export** | Prometheus metrics and webhook alerts exist; no OpenTelemetry traces or log-shipping integration | Days |

## Needed to be a competitive product (should fix)

* Per-route and per-client policies; allow-lists and persisted-query support. (Shadow / report-only mode is implemented.)
* Policy editing with review and rollback (today policy is file/env only, by design).
* Subscriptions (WebSocket), batched (array) requests (currently rejected with a clear 400), multipart uploads, automatic persisted queries.
* Retention controls, GDPR-style export/delete, PII-aware redaction rules configurable per field.
* Packaging: versioned releases, signed images, Helm chart / Terraform example, upgrade notes, SBOM.
* Security assurance: independent review or penetration test, fuzzing of the analyzer, threat-model sign-off.
* Evaluation: a public, labelled GraphQL-abuse corpus (or partnership data), drift monitoring, scheduled retraining.
* Legal/data: confirm the licence of `ml/data/*` (see `NOTICE.md`).

## A realistic path

1. **This week (demo-ready):** run Docker verification, fix findings, deploy a private demo behind Caddy with a client key.
2. **Month 1 (pilot-ready):** run shadow mode on a real API, Redis state, OIDC + roles, schema-aware cost, soak tests.
3. **Month 2-3 (v1):** validate on a real pilot API, tune and re-evaluate on real labels, packaging, security review.

Until steps 1-2 are done, describe it as a research/portfolio project with a working reference implementation, not as a
product for production traffic.
