# Roadmap

Living document. Last updated 2026-11-03.

## Wedge

Server-agnostic, schema-optional GraphQL protection where every decision is attributed to named rules, mapped to
OWASP API Security Top 10 (2023), with overhead measured against a no-gateway baseline and published next to
graphql-armor and Apollo Router demand control on a shared attack corpus.

Where existing tools already win (verified 2026-11-02): Apollo Router and Cosmo Router use the real (super)graph
schema, `@cost`/`@listSize`, per-subgraph limits and persisted-operation safelists; graphql-armor runs in-process
with no extra hop. Sentinel must not claim to beat them on cost accuracy unless Phase 1 shows it.

## Current state (verified)

* 199 tests pass (backend, sentinel_core, benchmarks).
* Detection numbers are synthetic and generator-labelled. Production blend: precision 0.79, FPR 0.237 on the
  synthetic test split. ML gain over rules alone is **not** measured on an independent corpus.
* Single process, in-memory limiter, ~160-180 req/s on one Windows machine; overhead not isolated from upstream.
* Done and verified: head-to-head benchmark, OWASP mapping, schema/federation-aware cost, persisted queries,
  batching, WebSocket subscriptions, OpenTelemetry, Envoy ext_proc (smoke-tested), Helm (lint/kubeconform), Grafana.
* Not done: ML retrain on current scikit-learn and independent ML-gain measurement (ML showed no gain on the
  held-out corpus), Redis shared limiter, PyPI release, public demo, load test of the Envoy path.

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 Hygiene | Verify CI claim, bump safe pins, create living docs | Done |
| 1 Benchmark corpus and harness | Labelled corpus, Sentinel vs graphql-armor vs Apollo Router, detection / FP / p50 / p99 vs baseline | Done |
| 2 Policy and OWASP mapping | Rule to OWASP / attack-class table, batching and persisted-query rules, retune defaults | Done |
| 3 Schema and federation-aware cost | SDL, `@cost`/`@listSize`, supergraph | Done |
| 4 Observability | OpenTelemetry, structured decision logs, Grafana JSON | Done |
| 5 Deployment | Envoy ext_proc / sidecar, Helm, Compose with vulnerable target, Redis state | Done except Redis state |
| 6 Library | Extract analyzer for PyPI, retrain model on current scikit-learn, measure ML on vs off | Library extracted; ML on vs off measured (no gain); retrain and PyPI release not done |
| 7 Demo and write-up | Public demo, paper, interview pack | Write-up done; hosted demo not done |

## Open items

* Product name: "GraphQL Sentinel" vs the uncommitted rename to "GraphQL Demand Control Gateway" (user decision).
* Whether the hosted demo may run a deliberately vulnerable app.
* Apollo Router licensing for the benchmark (free tier only, or licence key).
* Remote repo has leftover Dependabot branches/PRs from before its config was removed (not touched).
* Git history has out-of-order dates; decide whether to leave as is.
