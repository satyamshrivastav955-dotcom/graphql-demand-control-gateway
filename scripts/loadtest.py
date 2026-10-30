"""Load test: starts a private gateway + demo upstream with relaxed rate limits and drives mixed traffic through it.

    python scripts/loadtest.py --duration 20 --concurrency 32 [--attack-ratio 0.2] [--json out.json]

Reports throughput, latency percentiles per outcome, error counts and process memory. Numbers describe THIS
machine, a single gateway process and the in-memory demo upstream; they are a regression baseline, not a capacity
claim. Uses ports 18000/18001 and a temporary event database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GATEWAY, UPSTREAM = 18000, 18001

BENIGN = [
    '{ users(first: 5) { id name username } }',
    '{ user(id: "7") { name email posts(first: 3) { title comments(first: 2) { text } } } }',
    '{ posts(first: 10) { id title author { name } } }',
    '{ products(first: 20) { id name price stock } }',
    'query Page($n: Int) { users(first: $n) { name friends(first: 3) { name } } }',
    '{ me { id name role } }',
]


def deep(n: int) -> str:
    return "{ user(id: \"1\") { " + "friends { " * (n - 1) + "name" + " }" * (n - 1) + " } }"


# Only operations the gateway blocks outright, or that are cheap for the upstream. (A throttle-tier query such as a
# depth-12 friends chain is deliberately NOT included: forwarded to the unprotected demo upstream it expands to ~10^11
# field resolutions, which is exactly why the real throttle quota is small.)
ATTACKS = [
    deep(18),                                                                        # hard limit: depth
    "{ " + " ".join(f'a{i}: user(id: "{i}") {{ name }}' for i in range(70)) + " }",  # hard limit: aliases
    "{ " + " ".join(f'a{i}: user(id: "{i}") {{ name }}' for i in range(55)) + " }",  # hard limit: aliases (smaller)
    "{ __schema { queryType { name } } }",                                           # introspection, cheap upstream
]


def start_stack(tmp: str) -> list[subprocess.Popen]:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "SENTINEL_UPSTREAM_URL": f"http://127.0.0.1:{UPSTREAM}/graphql",
           "SENTINEL_API_TOKEN": "loadtest-token-0123456789", "SENTINEL_DB_PATH": os.path.join(tmp, "load.db"),
           "SENTINEL_THROTTLE__RATE_LIMIT": "10000000", "SENTINEL_THROTTLE__RISKY_QUOTA": "10000000",
           "SENTINEL_LIMITS__MAX_BODY_BYTES": "200000"}
    py = [sys.executable, "-m", "uvicorn"]
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    return [
        subprocess.Popen([*py, "demo.upstream.app:app", "--port", str(UPSTREAM), "--log-level", "error"], cwd=ROOT, env=env, **quiet),
        subprocess.Popen([*py, "backend.main:app", "--port", str(GATEWAY), "--log-level", "error"], cwd=ROOT, env=env, **quiet),
    ]


async def wait_ready(client: httpx.AsyncClient) -> None:
    for _ in range(120):
        try:
            r = await client.get("/api/health")
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    raise SystemExit("gateway did not become ready")


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1)))] if s else 0.0


async def worker(client: httpx.AsyncClient, deadline: float, ratio: float, rng: random.Random, out: list) -> None:
    while time.perf_counter() < deadline:
        attack = rng.random() < ratio
        q = rng.choice(ATTACKS if attack else BENIGN)
        t = time.perf_counter()
        try:
            r = await client.post("/graphql-proxy", json={"query": q})
            out.append((time.perf_counter() - t, r.status_code, attack))
        except httpx.HTTPError:
            out.append((time.perf_counter() - t, 0, attack))


def rss_mb(pid: int) -> float | None:
    try:
        import psutil
        return round(psutil.Process(pid).memory_info().rss / 1e6, 1)
    except Exception:  # noqa: BLE001 - psutil is optional
        return None


async def run(args) -> dict:
    tmp = tempfile.mkdtemp()
    procs = start_stack(tmp)
    try:
        limits = httpx.Limits(max_connections=args.concurrency * 2, max_keepalive_connections=args.concurrency)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{GATEWAY}", timeout=30, limits=limits) as client:
            await wait_ready(client)
            for q in BENIGN + ATTACKS:  # warm-up
                await client.post("/graphql-proxy", json={"query": q})
            samples: list = []
            rng = random.Random(1)
            start = time.perf_counter()
            deadline = start + args.duration
            await asyncio.gather(*[worker(client, deadline, args.attack_ratio, random.Random(i), samples)
                                   for i in range(args.concurrency)])
            elapsed = time.perf_counter() - start
            mem = rss_mb(procs[1].pid)
            _ = rng
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()

    by_status = Counter(s for _, s, _ in samples)
    lat_by = defaultdict(list)
    for dt, status, _ in samples:
        lat_by[{200: "allowed (forwarded)", 403: "blocked", 429: "throttled"}.get(status, f"status {status}")].append(dt * 1000)
    all_ms = [dt * 1000 for dt, _, _ in samples]
    return {
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "cpu": f"{platform.processor() or platform.machine()} ({os.cpu_count()} logical cores)"},
        "config": {"duration_s": args.duration, "concurrency": args.concurrency, "attack_ratio": args.attack_ratio,
                   "gateway_processes": 1, "upstream": "in-memory demo GraphQL server", "event_store": "SQLite file"},
        "requests": len(samples), "elapsed_s": round(elapsed, 2), "requests_per_second": round(len(samples) / elapsed, 1),
        "status_counts": dict(sorted(by_status.items())),
        "transport_errors": by_status.get(0, 0),
        "latency_ms": {"p50": round(pct(all_ms, 0.5), 1), "p95": round(pct(all_ms, 0.95), 1),
                       "p99": round(pct(all_ms, 0.99), 1), "max": round(max(all_ms), 1), "mean": round(statistics.fmean(all_ms), 1)},
        "latency_ms_by_outcome": {k: {"n": len(v), "p50": round(pct(v, 0.5), 1), "p95": round(pct(v, 0.95), 1), "p99": round(pct(v, 0.99), 1)}
                                  for k, v in sorted(lat_by.items())},
        "gateway_rss_mb_at_end": mem,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duration", type=float, default=20)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--attack-ratio", type=float, default=0.2)
    ap.add_argument("--json", help="write the full result to this file")
    args = ap.parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
