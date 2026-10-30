"""HTTP API: the GraphQL proxy plus the dashboard's read endpoints."""
from __future__ import annotations

import asyncio
import csv
import io
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from ..core.config import ROOT
from .gateway import ClientInfo, GraphQLGateway

router = APIRouter()
EVALUATION_FILE = ROOT / "ml" / "reports" / "evaluation.json"
TIERS = ("SAFE", "LOW_RISK", "MEDIUM_RISK", "HIGH_RISK", "CRITICAL")
DECISIONS = ("ALLOW", "THROTTLE", "BLOCK", "ERROR")


def _gw(request: Request) -> GraphQLGateway:
    gw = getattr(request.app.state, "gateway", None)
    if gw is None:
        raise HTTPException(status_code=503, detail="Gateway not initialised")
    return gw


def _client(request: Request) -> ClientInfo:
    gw = _gw(request)
    ip = request.client.host if request.client else "unknown"
    if gw.settings.gateway.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            ip = fwd.split(",")[0].strip() or ip
    return ClientInfo(ip=ip, client_id=request.headers.get("x-client-id"), headers=dict(request.headers))


def _admin(request: Request) -> GraphQLGateway:
    """Authenticate a management-API call and return the gateway."""
    gw = _gw(request)
    gw.auth.require(request, _client(request).ip)
    return gw


async def _read_json(request: Request, limit: int) -> Any:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail="Request body too large")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail="Request body too large")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks) or b"null")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Request body is not valid JSON") from None


@router.post("/graphql-proxy")
async def graphql_proxy(request: Request):
    gw = _gw(request)
    # Rejected before the body is read; unauthenticated requests are not recorded as events.
    gw.auth.require_client_key(request, _client(request).ip)
    body = await _read_json(request, gw.settings.limits.max_body_bytes)
    result = await gw.handle(body, _client(request))
    return JSONResponse(result.body, status_code=result.status, headers=result.headers)


@router.post("/api/analyze")
async def analyze_dry_run(request: Request):
    """Analyse an operation without forwarding or storing it (authenticated)."""
    gw = _admin(request)
    body = await _read_json(request, gw.settings.limits.max_body_bytes)
    q = body.get("query") if isinstance(body, dict) else None
    if not isinstance(q, str) or not q.strip():
        raise HTTPException(status_code=400, detail="A non-empty 'query' string is required")
    variables = body.get("variables")
    verdict = gw.evaluate(q, body.get("operationName"), variables if isinstance(variables, dict) else None)
    if verdict.decision == "ERROR":
        raise HTTPException(status_code=400, detail=verdict.error or "Invalid GraphQL operation")
    cfg = gw.settings.gateway
    return {
        "decision": verdict.decision, "risk_tier": verdict.risk_tier, "score": verdict.score,
        "rule_score": verdict.rule_score, "ml_score": verdict.ml_score, "features": verdict.features,
        "explanations": verdict.explanations, "limit_violations": verdict.limit_violations,
        "would_forward": verdict.decision != "BLOCK" and (cfg.mode == "simulation" or bool(cfg.upstream_url)),
        "latency_ms": round(verdict.latency_ms, 3),
    }


@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.get("/api/ready")
async def ready(request: Request):
    """Public: local checks only. Authenticated callers also get the upstream probe and check details."""
    gw = _gw(request)
    store_ok = gw.store.ping()
    if not gw.auth.is_authorised(request, _client(request).ip) or not gw.auth.required:
        # No upstream traffic is generated for unauthenticated callers.
        public_ok = store_ok and (gw.settings.gateway.mode == "simulation" or bool(gw.settings.gateway.upstream_url))
        return JSONResponse({"status": "ready" if public_ok else "degraded"}, status_code=200 if store_ok else 503)
    upstream = await gw.upstream_status()
    checks = {"model": gw.scorer.model_loaded, "store": store_ok, "upstream": upstream}
    ok = store_ok and upstream in ("ok", "simulation")
    return JSONResponse({"status": "ready" if ok else "degraded", "checks": checks},
                        status_code=200 if store_ok else 503)


@router.get("/api/config")
async def get_config(request: Request):
    gw = _admin(request)
    s = gw.settings
    model = gw.scorer.model
    meta = model.meta if model and model.loaded else {}
    host = urlparse(s.gateway.upstream_url).netloc.rsplit("@", 1)[-1] if s.gateway.upstream_url else None
    return {
        "version": s.app.version,
        "mode": s.gateway.mode,
        "upstream_configured": bool(s.gateway.upstream_url),
        "client_key_required": gw.auth.client_key_required,
        "enforcement": s.gateway.enforcement,
        "alerts_configured": gw.alerts.enabled,
        "upstream_host": host,
        "limits": s.limits.model_dump(),
        "introspection": s.security.introspection,
        "tiers": s.security.policy.risk_tier_thresholds.model_dump(),
        "tier_actions": s.security.policy.tier_actions,
        "throttle": {"rate_limit": s.throttle.rate_limit, "window_seconds": s.throttle.window_seconds,
                     "risky_quota": s.throttle.risky_quota},
        "ml_weight": gw.scorer.weight if gw.scorer.model_loaded else 0.0,
        "model": {"loaded": gw.scorer.model_loaded, "name": meta.get("name"),
                  "trained_at": meta.get("trained_at"), "n_features": len(meta.get("feature_names", [])) or None},
    }


@router.get("/api/events")
async def list_events(request: Request, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                      decision: Optional[str] = None, tier: Optional[str] = None, q: Optional[str] = None,
                      sort: str = Query("timestamp", pattern="^(timestamp|score)$"),
                      order: str = Query("desc", pattern="^(asc|desc)$")):
    store = _admin(request).store
    items, total = await asyncio.to_thread(store.list, limit, offset, decision, tier, q, sort, order)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


CSV_COLUMNS = ("id", "timestamp", "ip", "client_id", "operation_name", "operation_type", "decision", "enforced",
               "risk_tier", "score", "rule_score", "ml_score", "upstream_status", "latency_ms", "total_latency_ms",
               "limit_violations", "query")


def _csv_cell(value: Any) -> Any:
    """Neutralise spreadsheet formula injection (cells starting with = + - @ are prefixed with a quote)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@router.get("/api/events/export")
async def export_events(request: Request, format: str = Query("csv", pattern="^(csv|json)$"),
                        limit: int = Query(5000, ge=1, le=20000), decision: Optional[str] = None,
                        tier: Optional[str] = None, q: Optional[str] = None):
    """Download recent events (newest first) as CSV or JSON. Queries are already credential-redacted."""
    store = _admin(request).store
    rows: list = []
    offset = 0
    while len(rows) < limit:
        page, total = await asyncio.to_thread(store.list, min(500, limit - len(rows)), offset, decision, tier, q,
                                              "timestamp", "desc")
        rows.extend(page)
        offset += len(page)
        if not page or offset >= total:
            break
    if format == "json":
        return JSONResponse({"count": len(rows), "events": rows},
                            headers={"Content-Disposition": 'attachment; filename="sentinel-events.json"'})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for e in rows:
        row = dict(e)
        row["limit_violations"] = ";".join(e.get("limit_violations") or [])
        row["query"] = (e.get("query") or "")[:500]
        writer.writerow([_csv_cell(row.get(c)) for c in CSV_COLUMNS])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="sentinel-events.csv"'})


@router.get("/api/events/{event_id}")
async def get_event(request: Request, event_id: str):
    store = _admin(request).store
    event = await asyncio.to_thread(store.get, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event["client_timeline"] = await asyncio.to_thread(store.client_timeline, event.get("ip") or "")
    return event


@router.get("/api/metrics")
async def metrics(request: Request, minutes: int = Query(60, ge=1, le=1440)):
    store = _admin(request).store
    since = (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    rows = await asyncio.to_thread(store.window, since)
    decisions = Counter(r["decision"] for r in rows)
    tiers = Counter(r["risk_tier"] for r in rows if r["risk_tier"])
    scores = [r["score"] for r in rows if r["score"] is not None]
    lat = sorted(r["latency_ms"] for r in rows if r["latency_ms"] is not None)
    total = len(rows)

    buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "allowed": 0, "throttled": 0, "blocked": 0})
    signals: Counter = Counter()
    for r in rows:
        b = buckets[r["timestamp"][11:16]]
        b["total"] += 1
        key = {"ALLOW": "allowed", "THROTTLE": "throttled", "BLOCK": "blocked"}.get(r["decision"])
        if key:
            b[key] += 1
        if r["risk_tier"] in ("MEDIUM_RISK", "HIGH_RISK", "CRITICAL"):
            for e in json.loads(r["explanations"] or "[]"):
                if e.get("points", 0) > 0 or e.get("rule") == "hard_limit":
                    signals[e["rule"]] += 1

    items, _ = await asyncio.to_thread(store.list, 200, 0, None, None, None, "timestamp", "desc")
    suspicious = [e for e in items if e["decision"] in ("BLOCK", "THROTTLE")
                  or e["risk_tier"] in ("MEDIUM_RISK", "HIGH_RISK", "CRITICAL")][:8]
    return {
        "total_queries": total,
        "allowed_count": decisions["ALLOW"], "throttled_count": decisions["THROTTLE"],
        "blocked_count": decisions["BLOCK"], "error_count": decisions["ERROR"],
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "avg_latency_ms": round(sum(lat) / len(lat), 3) if lat else 0,
        "p95_latency_ms": round(lat[int(0.95 * (len(lat) - 1))], 3) if lat else 0,
        "block_rate": round(decisions["BLOCK"] / total, 4) if total else 0,
        "active_clients": len({r["ip"] for r in rows}),
        "tier_distribution": {t: tiers[t] for t in TIERS},
        "decision_distribution": {d: decisions[d] for d in DECISIONS},
        "load_over_time": [{"time": k, **v} for k, v in sorted(buckets.items())][-60:],
        "top_signals": [{"rule": k, "count": v} for k, v in signals.most_common(8)],
        "recent_suspicious": suspicious,
    }


@router.get("/metrics")
async def prometheus_metrics(request: Request):
    """Prometheus scrape endpoint (bearer token required; scrape the backend directly, not through the dashboard proxy)."""
    gw = _admin(request)
    model = gw.scorer.model.meta if gw.scorer.model and gw.scorer.model.loaded else {}
    gauges = {
        "sentinel_info": ("Build and mode information.", {
            "version": gw.settings.app.version, "mode": gw.settings.gateway.mode,
            "enforcement": gw.settings.gateway.enforcement, "model": str(model.get("name") or "none")}, 1),
        "sentinel_model_loaded": ("1 if the risk model is loaded.", {}, 1 if gw.scorer.model_loaded else 0),
        "sentinel_tracked_clients": ("Clients tracked by the rate limiter.", {}, gw.rate_limiter.tracked_keys()),
    }
    return PlainTextResponse(gw.metrics.render(gauges), media_type="text/plain; version=0.0.4")


@router.get("/api/live")
async def live(request: Request):
    """Server-sent events: every new audit event as it is recorded."""
    gw = _admin(request)
    store = gw.store
    if not gw.auth.open_stream():
        raise HTTPException(status_code=429, detail="Too many live streams")

    async def stream():
        try:
            last = await asyncio.to_thread(store.max_seq)
            yield ": connected\n\n"
            idle = 0
            while not await request.is_disconnected():
                events, last = await asyncio.to_thread(store.since, last)
                for ev in events:
                    yield f"data: {json.dumps(ev)}\n\n"
                idle = 0 if events else idle + 1
                if idle and idle % 15 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(1)
        finally:
            gw.auth.close_stream()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/evaluation")
async def evaluation():
    path: Path = EVALUATION_FILE
    if not path.exists():
        return {"available": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"available": False}
    return {"available": True, **data}
