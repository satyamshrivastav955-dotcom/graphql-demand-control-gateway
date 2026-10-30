"""End-to-end check against a running stack (see scripts/dev.py or docker compose).

    SENTINEL_API_TOKEN=<token> python scripts/e2e_check.py [--base http://127.0.0.1:8000]

Sends a legitimate query, high-risk and abusive queries, and verifies decisions, real upstream data,
throttling and that every request appears as an audit event. Exits non-zero on the first failure.
Only run it against a gateway you own: it deliberately sends abusive (but harmless) operations.
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx


def deep(n: int) -> str:
    return "{ " + "friends { " * (n - 1) + "name" + " }" * (n - 1) + " }"


def check(cond: bool, label: str, detail: str = "") -> None:
    print(("PASS  " if cond else "FAIL  ") + label + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--token", default=os.environ.get("SENTINEL_API_TOKEN"), help="management API token")
    args = ap.parse_args()
    if not args.token:
        sys.exit("Set SENTINEL_API_TOKEN or pass --token (the management API requires it)")
    c = httpx.Client(base_url=args.base, timeout=15)
    anon = httpx.Client(base_url=args.base, timeout=15)
    c.headers["Authorization"] = f"Bearer {args.token}"
    c.headers["X-API-Key"] = args.token  # accepted by /graphql-proxy when gateway client keys are enabled

    # 0. the management API is closed to anonymous callers; the public surface is minimal
    check(anon.get("/api/events").status_code == 401, "anonymous /api/events is rejected (401)")
    check(anon.post("/api/analyze", json={"query": "{ a }"}).status_code == 401, "anonymous dry-run is rejected (401)")
    check(anon.get("/api/ready").json() in ({"status": "ready"}, {"status": "degraded"}), "public readiness exposes status only")

    ready = c.get("/api/ready").json()
    check(ready["checks"]["upstream"] == "ok", "gateway can reach the upstream", str(ready))

    def post(q, **kw):
        r = c.post("/graphql-proxy", json={"query": q, **kw})
        return r, r.json().get("extensions", {}).get("security", {})

    # 1. legitimate query returns the upstream's real data
    r, sec = post("query { users(first: 2) { name username } }")
    check(r.status_code == 200 and sec["decision"] == "ALLOW", "legitimate query is allowed", r.text[:200])
    check(len(r.json()["data"]["users"]) == 2, "response is the upstream's real data")
    first_event = sec["event_id"]

    # 2. hard-limit violation is blocked and the upstream never sees it
    r, sec = post(deep(18))
    check(r.status_code == 403 and sec["decision"] == "BLOCK", "over-deep query is blocked (403)", r.text[:200])
    check(r.json()["data"] is None, "blocked response carries no data")
    check(any("max_depth" in v for v in sec["limit_violations"]), "block reason is explained")

    # 3. introspection is flagged (MEDIUM, or HIGH when the model agrees) but not hard-blocked by default
    r, sec = post("{ __schema { types { name } } }")
    check(r.status_code in (200, 429) and sec["risk_tier"] in ("MEDIUM_RISK", "HIGH_RISK"),
          "introspection is flagged as suspicious", str(sec.get("risk_tier")))

    # 4. high-risk operations are throttled once the per-client quota is spent
    codes = [post(deep(14))[0].status_code for _ in range(8)]
    check(200 in codes and 429 in codes, "high-risk operations are throttled after the quota", str(codes))
    limited = c.post("/graphql-proxy", json={"query": deep(14)})
    check(limited.status_code == 429 and "retry-after" in limited.headers, "429 carries Retry-After")

    # 5. dry run does not create events
    before = c.get("/api/events", params={"limit": 1}).json()["total"]
    dry = c.post("/api/analyze", json={"query": deep(14)})
    check(dry.status_code == 200 and dry.json()["decision"] in ("THROTTLE", "BLOCK"), "dry-run analysis works")
    check(c.get("/api/events", params={"limit": 1}).json()["total"] == before, "dry run stored nothing")

    # 6. everything is visible as audit events
    ev = c.get(f"/api/events/{first_event}")
    check(ev.status_code == 200 and ev.json()["upstream_status"] == 200, "allowed request recorded with upstream status")
    blocked = c.get("/api/events", params={"decision": "BLOCK"}).json()
    check(blocked["total"] >= 1 and blocked["items"][0]["upstream_status"] is None,
          "blocked request recorded and never forwarded")
    m = c.get("/api/metrics").json()
    check(m["total_queries"] >= 12 and m["blocked_count"] >= 1 and m["throttled_count"] >= 1, "metrics reflect traffic")
    print("\nAll end-to-end checks passed.")


if __name__ == "__main__":
    main()
