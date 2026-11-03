### Attack detection (share of attacks that did not reach the executor)

| Attack class | OWASP API 2023 | n | baseline | sentinel | sentinel-schema | sentinel-rules | armor-default | armor-matched | router |
|---|---|---|---|---|---|---|---|---|---|
| deep_nesting | API4 | 40 | 0% | 100% | 100% | 100% | 100% | 100% | 0% |
| fragment_bomb | API4 | 40 | 0% | 100% | 100% | 100% | 100% | 100% | 0% |
| list_amplification | API4 | 40 | 0% | 100% | 100% | 100% | 100% | 100% | 0% |
| alias_flood | API4 | 40 | 0% | 100% | 100% | 100% | 100% | 100% | 0% |
| credential_stuffing | API2, API4 | 40 | 0% | 100% | 100% | 100% | 100% | 55% | 0% |
| batching | API2, API4 | 40 | 0% | 100% | 100% | 100% | 0% | 0% | 100% |
| directive_overload | API4 | 40 | 0% | 100% | 100% | 100% | 100% | 100% | 0% |
| token_bloat | API4 | 40 | 100% | 100% | 100% | 100% | 100% | 0% | 0% |
| introspection_abuse | API8, API9 | 40 | 25% | 100% | 100% | 100% | 25% | 25% | 100% |
| suggestion_probe | API8, API9 | 30 | 3% | 100% | 100% | 100% | 100% | 100% | 100% |
| sensitive_enumeration | API1, API3 | 40 | 0% | 100% | 100% | 100% | 100% | 62% | 0% |
| stay_under | API4 | 40 | 0% | 100% | 100% | 100% | 100% | 100% | 0% |
| **macro average** | | | **11%** | **100%** | **100%** | **100%** | **85%** | **70%** | **25%** |
| pooled (95% CI) | | | 11% (8-14) | 100% (99-100) | 100% (99-100) | 100% (99-100) | 85% (82-88) | 70% (65-74) | 23% (20-27) |

### False positives (share of benign operations that did not get a normal answer)

| Benign group | n | baseline | sentinel | sentinel-schema | sentinel-rules | armor-default | armor-matched | router |
|---|---|---|---|---|---|---|---|---|
| alias_batch_ui | 40 | 0% | 100% | 0% | 100% | 90% | 0% | 0% |
| aliased_readable | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| batch_small | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| dashboard | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| deep_cheap | 40 | 0% | 0% | 0% | 0% | 100% | 0% | 0% |
| fragments | 40 | 0% | 0% | 0% | 0% | 100% | 0% | 0% |
| list_page | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| lookup | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| mutation | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| nested_view | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| variables | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| wide_page | 40 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| wide_report | 40 | 0% | 88% | 0% | 88% | 68% | 0% | 0% |
| **all typical** (95% CI) | 360 | **0% (0-1)** | **0% (0-1)** | **0% (0-1)** | **0% (0-1)** | **11% (8-15)** | **0% (0-1)** | **11% (8-15)** |
| **all heavy_legit** (95% CI) | 160 | **0% (0-2)** | **47% (39-55)** | **0% (0-2)** | **47% (39-55)** | **64% (57-71)** | **0% (0-2)** | **0% (0-2)** |

### Work reaching the upstream from attacks

| System | Field resolutions executed (sum over all attacks, capped at 100,000 per operation) |
|---|---|
| No gateway (Python demo upstream) | 16,015,590 |
| Sentinel (shipped defaults, ML on) | 0 |
| Sentinel + schema (cost from SDL, ML on) | 0 |
| Sentinel (rules only, ML off) | 0 |
| graphql-armor 3.2.0 (documented defaults) | 5,640 |
| graphql-armor 3.2.0 (limits widened to Sentinel's) | 7,970 |
| Apollo Router 2.12 (unlicensed defaults) | 15,992,840 |

### Latency on benign traffic (median of repetitions; lower is better)

| System | c=1 p50 ms | c=1 p99 ms | c=16 req/s | c=16 p50 ms | c=16 p99 ms | errors |
|---|---|---|---|---|---|---|
| No gateway (Python demo upstream) | 19.5 | 29.5 | 64 | 125.3 | 1431.7 | 0 |
| Sentinel (shipped defaults, ML on) | 15.8 | 30.7 | 107 | 138.1 | 317.9 | 0 |
| Sentinel + schema (cost from SDL, ML on) | 19.2 | 51.5 | 107 | 139.6 | 285.1 | 0 |
| Sentinel (rules only, ML off) | 20.8 | 36.2 | 134 | 86.8 | 728.6 | 0 |
| Apollo Router 2.12 (unlicensed defaults) | 9.9 | 17.0 | 190 | 36.5 | 608.9 | 0 |
| Node/Yoga server, no protection | 2.9 | 7.6 | 218 | 40.0 | 357.3 | 0 |
| graphql-armor 3.2.0 (documented defaults) | 3.0 | 7.8 | 221 | 40.9 | 332.9 | 0 |
| graphql-armor 3.2.0 (limits widened to Sentinel's) | 2.8 | 5.9 | 226 | 37.9 | 337.8 | 0 |

Added latency vs the system's own unprotected baseline (c=1):

| System | baseline | +p50 ms | +p99 ms |
|---|---|---|---|
| Sentinel (shipped defaults, ML on) | baseline | -3.7 | +1.2 |
| Sentinel + schema (cost from SDL, ML on) | baseline | -0.3 | +22.0 |
| Sentinel (rules only, ML off) | baseline | +1.2 | +6.7 |
| Apollo Router 2.12 (unlicensed defaults) | baseline | -9.6 | -12.6 |
| graphql-armor 3.2.0 (documented defaults) | armor-off | +0.1 | +0.2 |
| graphql-armor 3.2.0 (limits widened to Sentinel's) | armor-off | -0.1 | -1.7 |
