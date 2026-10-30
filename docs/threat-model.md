# Threat model

## What Sentinel is for

Protecting a GraphQL endpoint you operate from **operation-level abuse** by unauthenticated or low-privilege
clients: resource exhaustion and reconnaissance carried in a single, syntactically valid request.

| Threat | Mechanism | Control |
|---|---|---|
| Deep nesting / circular relations | `friends { friends { … } }` | Depth feature, `max_depth` hard limit |
| Fragment amplification | Fragments that spread each other repeatedly | Memoised fragment resolution, field-count saturation, cycle detection |
| Hidden depth | Nesting spread across fragments | Depth computed through fragments |
| Alias batching | Hundreds of aliased lookups or logins in one request | Alias count, `max_aliases`, credential-stuffing signal |
| Field duplication | Same field repeated | Duplicate-field feature |
| List amplification | Nested `first: 1000` lists | Cost model with list multipliers, `max_complexity` |
| Directive overload | Hundreds of `@include`/`@skip` | Directive count |
| Introspection reconnaissance | `__schema` / `__type` | `introspection: allow \| flag \| block` |
| Sensitive-field enumeration | Aliased lookups of `email`/`token` fields | Sensitive-field feature |
| Oversized / pathological input | Huge bodies, thousands of tokens, parser recursion | Body, length and token limits; parser failures become BLOCK, not 500 |
| Request floods | Many requests from one client | Per-IP sliding window; bounded state |

## Trust boundaries and assumptions

* The configured **upstream is trusted**; the gateway forwards to exactly one URL and never to a client-supplied one.
* Sentinel must be the **only network path** to the upstream (network policy / private network). It does not
  protect an upstream that is reachable directly.
* **Authentication and authorisation stay in the upstream.** Sentinel forwards `Authorization` and `X-Request-ID`
  only; cookies are dropped.
* Client identity for throttling is the **IP address**. Behind a reverse proxy enable
  `gateway.trust_proxy_headers` *and* make sure the proxy overwrites `X-Forwarded-For`; otherwise clients can
  spoof it. Clients behind one NAT share a quota.
* The model file is loaded with `joblib` (pickle). It is trusted only if its SHA-256 and feature list match the
  metadata that ships with it; never point the gateway at a model you did not build.

## Handling of sensitive data

* GraphQL **variables are never stored**. String literals passed to credential-like arguments
  (`password`, `token`, `secret`, `apiKey`, ...) are replaced with `[REDACTED]` before an event is persisted.
  Other literals in the query text are stored as sent, so treat the event database as sensitive.
* Errors returned to clients are generic. Upstream error bodies, hostnames and exception text are not relayed.
* `/api/config` exposes the upstream **host** only, never credentials in the URL.
* The management API (`/api/*` except health, evaluation and a minimal readiness) requires a bearer token, with
  constant-time comparison, per-IP lockout after repeated failures and per-IP rate limiting. It is a **single shared
  token with full access**: no roles, no per-user audit, rotation needs a restart. No endpoint changes policy.
* `/graphql-proxy` is anonymous by default and can require an `X-API-Key` (`SENTINEL_GATEWAY_KEYS`); see
  [deployment](deployment.md) for the resulting exposure. Client keys are shared secrets with no per-key quotas.

## Out of scope / known limitations

* Not a WAF: no protection against injection inside resolvers, broken authorisation, or CSRF.
* Persisted queries, subscriptions over WebSockets and batched (array) requests are not supported.
* Detection is heuristic and statistical. The evaluation uses synthetic operations from a fictional schema; see
  [evaluation](evaluation.md) for what it does and does not show. Expect false positives on unusually heavy but
  legitimate queries (tune `limits.*` and `security.policy.*` to your API).
* In-memory rate limiting and behaviour state are per process. Run one gateway instance per upstream, or put a
  shared limiter in front, if you scale horizontally.
* The alert webhook URL is a secret supplied by the operator: it is never logged, returned by the API or included in metrics,
  and alerts omit query text unless `alerts.include_query` is enabled (credentials are redacted either way).
* The token travels in a header: serve the dashboard over TLS (see [deployment](deployment.md)).
* A determined attacker who stays under every limit and score threshold is allowed through by design.
