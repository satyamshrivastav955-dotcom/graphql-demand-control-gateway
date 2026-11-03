# Benchmarks

Living document. Every number in the README or on a resume must trace to a section here and a command that
reproduces it. Negative results are kept.

## Headline (held-out corpus, run once, 2026-11-03)

Seven systems on the same 990-operation corpus (seed 20270314, never used to tune anything). "Stopped" means the
operation did **not** reach the upstream executor, measured with the upstream's own work counters, not by error text.

| System | Attacks stopped (pooled, 95% CI) | Typical benign blocked | Heavy-but-legit blocked | Attack work reaching upstream |
|---|---|---|---|---|
| No gateway | 11% (8-14) | 0% | 0% | 16,015,590 field resolutions |
| **Sentinel, shipped defaults** | **100% (99-100)** | 0% (0-1) | **47% (39-55)** | 0 |
| **Sentinel + schema (cost from SDL)** | **100% (99-100)** | 0% (0-1) | **0% (0-2)** | 0 |
| Sentinel rules only (ML off) | 100% (99-100) | 0% (0-1) | 47% (39-55) | 0 |
| graphql-armor 3.2.0, documented defaults | 85% (82-88) | 11% (8-15) | 64% (57-71) | 5,640 |
| graphql-armor 3.2.0, limits widened | 70% (65-74) | 0% (0-1) | 0% (0-2) | 7,970 |
| Apollo Router 2.12, unlicensed | 23% (20-27) | 11% (8-15) | 0% (0-2) | 15,992,840 |

Full per-class tables: [`benchmarks/results/heldout.md`](benchmarks/results/heldout.md); raw:
`benchmarks/results/heldout.json`.

### What this does and does not show

* **Schema matters.** Without a schema Sentinel cannot tell a wide-but-cheap UI query from a costly one and blocks
  47% of the "heavy legitimate" group (all of `alias_batch_ui`, 88% of `wide_report`). With the SDL loaded
  (`SENTINEL_SCHEMA_PATH`) that false-positive rate drops to 0% at the same 100% detection. The shipped default
  (no schema) is therefore the weaker configuration; use the schema for anything real.
* **graphql-armor** is strong and almost free (+0.1 ms p50) but its defaults miss batching and block 64% of the heavy
  legitimate group; widening its limits to avoid that costs it 15 points of detection (token bloat, credential
  stuffing). Tuning is a real trade-off for it; Sentinel+schema did not need one on this corpus.
* **Apollo Router** here is the *unlicensed* router: demand control, depth and alias limits need a GraphOS licence
  (verified 2026-11-02), so it only stops batching, introspection and suggestion probes. This is not a verdict on
  the licensed product.
* **ML adds nothing measurable here.** Sentinel with and without the model has identical detection and false-positive
  numbers on this corpus. The rules do the work; the model has not been shown to help on an independent corpus.
* **Latency is not cleanly isolated.** Sentinel adds a hop and a Python process: +1 to +22 ms p99 at c=1 (the schema variant is the +22) against the
  Python upstream, but that upstream is itself noisy (its p50 moved from 8 to 19 ms between runs), so negative
  "added" values in the table are noise, not speedups. Throughput at c=16 (about 107-134 req/s) is well below
  the Node and Router targets (190-230 req/s). Sentinel is the slowest system here; graphql-armor, being in-process,
  is the cheapest.
* **The corpus is mine.** I wrote the generator and the labels. The held-out profile uses a different seed and
  sizes attacks to sit under common limits ("stay_under"), but the author of the corpus is also the author of the
  system. Treat the 100% as "no misses on this corpus", not as a general guarantee. The dev corpus was used to tune
  Sentinel after a first run in which it scored below graphql-armor on false positives (62% vs 82% on heavy-legit);
  that history is why the held-out run exists.
* Hardware: Windows 11, Docker Desktop (16 CPUs visible, 8 GB), each target limited to 2 CPUs / 1 GB, load
  generator on the same machine, 3 repetitions, median reported.

## Reproduce

```bash
docker compose -f benchmarks/docker-compose.yml up -d --build
PYTHONPATH=. python -m benchmarks.harness.run_benchmark --corpus benchmarks/corpus/corpus-heldout.json --out benchmarks/results/heldout.json   # ~25 min
PYTHONPATH=. python -m benchmarks.harness.report benchmarks/results/heldout.json --corpus benchmarks/corpus/corpus-heldout.json
python -m benchmarks.corpus.gen_corpus --help   # regenerate corpora
```

## Other measured results

| Item | Where | Caveat |
|---|---|---|
| Detection on synthetic split (combined: P 0.79, R 0.99, F1 0.88, FPR 0.237) | `ml/reports/evaluation.md`, `python -m ml.run --seed 42` | Synthetic, one fictional schema, generator-labelled; thresholds revised after seeing aggregates |
| FPR 3.4% on 208 real queries | same | NL2GQL test set; not abuse-shaped traffic |
| Envoy ext_proc path (2026-11-03) | `deploy/envoy` | Smoke test only: benign allowed, deep/alias abuse blocked at Envoy, metrics exposed. Not load tested |
| Observability profile (2026-11-03) | `docker compose --profile observability up` | Prometheus scrapes the backend (up), Grafana dashboard provisioned. Jaeger traces not inspected |
| Test suite | `python -m pytest` | 199 passed |
