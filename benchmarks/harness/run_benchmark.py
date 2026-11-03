"""Head-to-head benchmark harness.

    docker compose -f benchmarks/docker-compose.yml up -d --build
    python -m benchmarks.harness.run_benchmark                 # detection + false positives + latency
    python -m benchmarks.harness.run_benchmark --targets sentinel armor-default --skip-latency

For every corpus item the harness records whether the operation *reached the upstream executor*, using the upstream's
own counters (``/__stats``) read before and after each request. That is the ground truth for "was the attack stopped":
it does not depend on how a tool words its error. Suggestion-probe items instead check whether the response leaks
"Did you mean" suggestions. Latency uses benign traffic only and is compared with each tool's own unprotected baseline.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = ROOT / "results"
CORPUS = ROOT / "corpus" / "corpus.json"  # default (dev) corpus

PY_STATS = "http://127.0.0.1:18001/__stats"
TARGETS: Dict[str, Dict[str, Any]] = {
    "baseline": dict(url="http://127.0.0.1:18001/graphql", stats=PY_STATS, baseline_of=None,
                     label="No gateway (Python demo upstream)"),
    "sentinel": dict(url="http://127.0.0.1:18010/graphql-proxy", stats=PY_STATS, baseline="baseline",
                     label="Sentinel (shipped defaults, ML on)"),
    "sentinel-schema": dict(url="http://127.0.0.1:18012/graphql-proxy", stats=PY_STATS, baseline="baseline",
                            label="Sentinel + schema (cost from SDL, ML on)"),
    "sentinel-rules": dict(url="http://127.0.0.1:18011/graphql-proxy", stats=PY_STATS, baseline="baseline",
                           label="Sentinel (rules only, ML off)"),
    "router": dict(url="http://127.0.0.1:18030/graphql", stats=PY_STATS, baseline="baseline",
                   label="Apollo Router 2.12 (unlicensed defaults)"),
    "armor-off": dict(url="http://127.0.0.1:18020/graphql", stats="http://127.0.0.1:18020/__stats", baseline=None,
                      label="Node/Yoga server, no protection"),
    "armor-default": dict(url="http://127.0.0.1:18021/graphql", stats="http://127.0.0.1:18021/__stats",
                          baseline="armor-off", label="graphql-armor 3.2.0 (documented defaults)"),
    "armor-matched": dict(url="http://127.0.0.1:18022/graphql", stats="http://127.0.0.1:18022/__stats",
                          baseline="armor-off", label="graphql-armor 3.2.0 (limits widened to Sentinel's)"),
}


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def stats(client: httpx.Client, url: str) -> Dict[str, int]:
    return client.get(url, timeout=10).json()


def _answered(status: int, r: httpx.Response) -> bool:
    """True if the request got a real answer: HTTP 200 and every operation returned data without errors."""
    if status != 200:
        return False
    try:
        body = r.json()
    except ValueError:
        return False
    parts = body if isinstance(body, list) else [body]
    return all(isinstance(p, dict) and p.get("data") is not None and not p.get("errors") for p in parts)


def run_detection(name: str, cfg: Dict[str, Any], items: List[dict]) -> List[dict]:
    out: List[dict] = []
    with httpx.Client(timeout=30, limits=httpx.Limits(max_keepalive_connections=4)) as c:
        for it in items:
            before = stats(c, cfg["stats"])
            t0 = time.perf_counter()
            try:
                r = c.post(cfg["url"], json=it["body"])
                status, text, hdr = r.status_code, r.text, r.headers
                ok = _answered(status, r)
            except httpx.HTTPError as exc:
                status, text, hdr, ok = 0, f"transport error: {exc}", {}, False
            ms = (time.perf_counter() - t0) * 1000
            after = stats(c, cfg["stats"])
            executed = after["operations"] - before["operations"]
            out.append({
                "id": it["id"], "status": status, "ms": round(ms, 2), "executed_ops": executed,
                "aborted": after["aborted"] - before["aborted"], "work": after["work"] - before["work"],
                "ok": ok, "leaked_suggestion": "Did you mean" in text, "bytes": len(text),
                "decision": hdr.get("x-sentinel-decision") if hdr else None,
            })
    return out


async def _load(url: str, bodies: List[dict], concurrency: int, n: int) -> Dict[str, Any]:
    lat: List[float] = []
    errors = 0
    idx = 0
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=concurrency,
                                                                   max_keepalive_connections=concurrency)) as c:
        async def worker():
            nonlocal idx, errors
            while True:
                i = idx
                if i >= n:
                    return
                idx += 1
                t0 = time.perf_counter()
                try:
                    r = await c.post(url, json=bodies[i % len(bodies)])
                    if r.status_code != 200:
                        errors += 1
                except httpx.HTTPError:
                    errors += 1
                lat.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        await asyncio.gather(*[worker() for _ in range(concurrency)])
        wall = time.perf_counter() - t0
    lat.sort()
    return {"concurrency": concurrency, "n": len(lat), "errors": errors, "rps": round(len(lat) / wall, 1),
            "p50": round(pct(lat, .50), 2), "p95": round(pct(lat, .95), 2), "p99": round(pct(lat, .99), 2),
            "mean": round(statistics.fmean(lat), 2)}


def run_latency(cfg: Dict[str, Any], bodies: List[dict], reps: int, n1: int, n16: int) -> Dict[str, Any]:
    asyncio.run(_load(cfg["url"], bodies, 4, 300))  # warm-up (model load, connection pools, JIT)
    res: Dict[str, Any] = {"c1": [], "c16": []}
    for _ in range(reps):
        res["c1"].append(asyncio.run(_load(cfg["url"], bodies, 1, n1)))
        res["c16"].append(asyncio.run(_load(cfg["url"], bodies, 16, n16)))
    return res


def environment() -> Dict[str, Any]:
    env: Dict[str, Any] = {"platform": platform.platform(), "python": platform.python_version(),
                           "when": datetime.now(UTC).isoformat(timespec="seconds")}
    try:
        info = json.loads(subprocess.run(["docker", "info", "--format", "{{json .}}"], capture_output=True, text=True,
                                         timeout=30).stdout)
        env["docker"] = {k: info.get(k) for k in ("ServerVersion", "OperatingSystem", "NCPU", "MemTotal", "Name")}
    except Exception:  # noqa: BLE001
        env["docker"] = None
    try:
        out = subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "images", "--format", "json"],
                             capture_output=True, text=True, timeout=30).stdout
        env["images"] = out.strip()[:4000]
    except Exception:  # noqa: BLE001
        pass
    return env


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="*", default=list(TARGETS))
    ap.add_argument("--skip-detection", action="store_true")
    ap.add_argument("--skip-latency", action="store_true")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--n1", type=int, default=1500)
    ap.add_argument("--n16", type=int, default=4000)
    ap.add_argument("--out", default=None)
    ap.add_argument("--corpus", default=str(CORPUS), help="corpus json (dev: corpus.json, held-out: corpus-heldout.json)")
    args = ap.parse_args()

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    items = corpus["items"]
    lat_bodies = [i["body"] for i in items if i["label"] == "benign" and i["group"] == "typical"
                  and i["cls"] not in ("batch_small", "mutation")]
    result: Dict[str, Any] = {"environment": environment(), "corpus": {k: corpus.get(k) for k in ("profile", "seed", "attack_work_min", "benign_work_max")},
                              "args": vars(args), "targets": {}}
    for name in args.targets:
        cfg = TARGETS[name]
        print(f"== {name}: {cfg['label']}", flush=True)
        entry: Dict[str, Any] = {"label": cfg["label"], "baseline": cfg.get("baseline")}
        if not args.skip_detection:
            t0 = time.time()
            entry["detection"] = run_detection(name, cfg, items)
            print(f"   detection pass: {len(items)} requests in {time.time() - t0:.0f}s", flush=True)
        if not args.skip_latency:
            entry["latency"] = run_latency(cfg, lat_bodies, args.reps, args.n1, args.n16)
            r = entry["latency"]["c1"][-1]
            print(f"   c=1 p50 {r['p50']} ms p99 {r['p99']} ms | c=16 {entry['latency']['c16'][-1]['rps']} rps", flush=True)
        result["targets"][name] = entry
    RESULTS.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else RESULTS / f"raw-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(result), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
