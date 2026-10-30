# Performance

Measured with `python scripts/loadtest.py` (raw results: [`performance-results.json`](performance-results.json)).
The script starts a private gateway and the in-memory demo upstream with relaxed rate limits and drives a mix of
80% ordinary and 20% hard-blocked operations (depth, alias and introspection abuse) for 15-20 seconds.

**Environment:** Windows 11, Python 3.13, 16 logical cores, **load generator, gateway and upstream on the same machine**,
one gateway process (one uvicorn worker), SQLite event store on local disk. No TLS, no real network.

| Concurrency | Throughput | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| 1 | 77 req/s | 11 ms | 23 ms | 35 ms | 0 |
| 4 | 177 req/s | 20 ms | 42 ms | 58 ms | 0 |
| 32 | 162 req/s | 171 ms | 412 ms | 610 ms | 0 |

Gateway resident memory at the end of each run: about 211-220 MB (includes the loaded model and scikit-learn).

## How to read this

* **One process saturates at roughly 160-180 requests/second here.** Past that, extra concurrency only adds queueing:
  at 32 concurrent clients the 171 ms median is queueing delay (32 / 162 per second is about 0.2 s), not slower processing.
  That is about 6 ms of CPU per request, including parsing, feature extraction, scoring, the SQLite audit write and the
  upstream round trip.
* **Blocked requests are not much cheaper than forwarded ones** (similar latency), because analysis and the audit write
  dominate; the upstream call is fast in this setup. Against a slow real upstream the forwarded path will be slower.
* **Headroom comes from processes, not threads.** Run several gateway processes behind a load balancer. That is only
  correct once rate-limit and behaviour state are shared (Redis), which is not implemented; see
  [product readiness](product-readiness.md). Until then, run one gateway per upstream.
* The earlier in-process benchmark in the evaluation report (about 4-7 ms p50 per proxied request, stub upstream) agrees
  with the single-client figure here.

## Not measured

Long soak runs, memory growth over hours, behaviour with a slow or failing upstream under load, multi-process scaling,
TLS overhead, a Linux production host. Treat these numbers as a regression baseline for this repository, not a capacity
claim. Re-run the script before and after performance-sensitive changes.

## A lesson the load test taught

An earlier run mixed in a depth-12 query. It is below the hard limit, so it scores HIGH_RISK and is *throttled* (forwarded
within a small per-client quota). With the quota relaxed for the test, those queries reached the deliberately unprotected
demo upstream, which expanded each into roughly 10^11 field resolutions and stalled everything (64 of 74 requests timed
out). That is exactly the abuse the gateway exists to stop, and it shows why the default throttle quota is small (5 per
minute per client) and why THROTTLE is not a substitute for BLOCK on an upstream that cannot protect itself. If your
upstream cannot survive a high-risk operation, set `security.policy.tier_actions.HIGH_RISK` to `BLOCK`.
