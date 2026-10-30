"""GraphQL security gateway: analyse -> score -> decide -> enforce -> forward -> audit."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import httpx

from ..core.analysis import AnalysisError, TooComplexToParse, analyze
from ..core.config import Settings
from ..core.features.behavioral_store import BehavioralStore
from ..core.runtime.alerts import AlertDispatcher
from ..core.runtime.events import EventStore
from ..core.runtime.limiter import SlidingWindowLimiter
from ..core.runtime.metrics import Metrics
from ..core.security_engine.limits import check_limits
from ..core.security_engine.policy import SecurityPolicy
from ..core.security_engine.scorer import SecurityScorer, tier_for
from .auth import AdminAuth

logger = logging.getLogger(__name__)

_CLIENT_ID = re.compile(r"[^A-Za-z0-9_.:-]")


@dataclass
class ClientInfo:
    ip: str = "unknown"
    client_id: Optional[str] = None
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        if self.client_id:
            return _CLIENT_ID.sub("", self.client_id)[:64] or self.ip
        return self.ip


@dataclass
class Verdict:
    decision: str
    risk_tier: Optional[str]
    score: Optional[float]
    rule_score: Optional[float]
    ml_score: Optional[float]
    features: Dict[str, float]
    explanations: List[dict]
    limit_violations: List[str]
    operation_name: Optional[str]
    operation_type: Optional[str]
    latency_ms: float
    error: Optional[str] = None


@dataclass
class GatewayResponse:
    status: int
    body: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)


class GraphQLGateway:
    def __init__(self, settings: Settings, store: EventStore, scorer: Optional[SecurityScorer] = None,
                 http_client: Optional[httpx.AsyncClient] = None, alert_client: Optional[httpx.AsyncClient] = None):
        self.settings = settings
        self.metrics = Metrics()
        self.alerts = AlertDispatcher(settings.alerts, self.metrics, alert_client)
        self.store = store
        self.scorer = scorer or SecurityScorer(settings.security.policy, settings.security.introspection)
        self.policy = SecurityPolicy(settings.security.policy)
        t = settings.throttle
        self.rate_limiter = SlidingWindowLimiter(t.rate_limit, t.window_seconds, t.max_tracked_clients)
        self.risky_limiter = SlidingWindowLimiter(t.risky_quota, t.window_seconds, t.max_tracked_clients)
        self.behavior = BehavioralStore(window_seconds=t.window_seconds, max_clients=t.max_tracked_clients)
        a = settings.api
        self.auth = AdminAuth(a.token, a.auth_required, a.auth_failures, a.auth_window_seconds,
                              a.rate_limit_per_minute, a.max_live_streams, settings.gateway.client_keys)
        self._client = http_client
        self._owns_client = http_client is None

    # -- lifecycle ----------------------------------------------------------------------
    async def startup(self) -> None:
        # Warm the analyzer and model so the first real request does not pay ~2 s of lazy initialisation.
        await asyncio.to_thread(self.evaluate, "{ __typename }")
        await self.alerts.start()
        if self._client is None:
            g = self.settings.gateway
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(g.upstream_timeout_seconds, connect=min(5.0, g.upstream_timeout_seconds)),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                follow_redirects=False,
            )

    async def shutdown(self) -> None:
        await self.alerts.stop()
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None

    async def upstream_status(self) -> str:
        g = self.settings.gateway
        if g.mode == "simulation":
            return "simulation"
        if not g.upstream_url:
            return "not_configured"
        try:
            assert self._client is not None
            resp = await self._client.post(
                g.upstream_url, json={"query": "{ __typename }"}, timeout=min(3.0, g.upstream_timeout_seconds))
            return "ok" if resp.status_code < 500 else "unreachable"
        except Exception:  # noqa: BLE001
            return "unreachable"

    # -- analysis -----------------------------------------------------------------------
    def evaluate(self, query: str, operation_name: Optional[str] = None, variables: Optional[dict] = None,
                 behavior_key: Optional[str] = None) -> Verdict:
        start = time.perf_counter()
        s = self.settings
        empty: Dict[str, Any] = dict(features={}, explanations=[], operation_name=None, operation_type=None)
        if len(query) > s.limits.max_query_length * 4:
            # Refuse to even tokenise absurdly large inputs.
            return Verdict("BLOCK", "CRITICAL", 100.0, 100.0, None, limit_violations=["query_length"],
                           latency_ms=_ms(start), **empty)
        try:
            analysis = analyze(query, operation_name, variables, s.limits.max_tokens)
        except TooComplexToParse:
            return Verdict("BLOCK", "CRITICAL", 100.0, 100.0, None, limit_violations=["parse_budget_exceeded"],
                           latency_ms=_ms(start), **empty)
        except AnalysisError as exc:
            return Verdict("ERROR", None, None, None, None, limit_violations=[], latency_ms=_ms(start),
                           error=str(exc), **empty)

        features = analysis.features
        behavior = self.behavior.features(behavior_key) if behavior_key else None
        scored = self.scorer.score(features, behavior)
        violations = check_limits(features, s.limits, s.security.introspection,
                                  analysis.fragment_cycle, analysis.unknown_fragments)
        score, tier = scored["score"], scored["risk_tier"]
        if violations:
            # Hard limits can only raise severity, never lower it.
            thr = s.security.policy.risk_tier_thresholds
            score = max(score, thr.high_risk + 1)
            tier = tier_for(score, thr)
            scored["explanations"].insert(0, {
                "rule": "hard_limit", "feature": "limits", "value": ", ".join(violations),
                "points": 0, "severity": "high",
                "description": "Hard limit exceeded: " + ", ".join(violations),
            })
        return Verdict(
            decision=self.policy.decide(tier, violations), risk_tier=tier, score=score,
            rule_score=scored["rule_score"], ml_score=scored["ml_score"], features=features,
            explanations=scored["explanations"], limit_violations=violations,
            operation_name=analysis.operation_name, operation_type=analysis.operation_type,
            latency_ms=_ms(start),
        )

    # -- request handling ---------------------------------------------------------------
    async def handle(self, body: Any, client: ClientInfo) -> GatewayResponse:
        t0 = time.perf_counter()
        problem = _validate_body(body)
        if problem:
            return GatewayResponse(400, _error(problem, "ERROR", "rejected"), {"X-Sentinel-Decision": "ERROR"})
        query, op_name, variables = body["query"], body.get("operationName"), body.get("variables")

        allowed, retry = self.rate_limiter.check(client.ip)
        if not allowed:
            return await self._finish_unscored(query, client, t0, retry)

        verdict = self.evaluate(query, op_name, variables, behavior_key=client.ip)
        self.behavior.record(client.ip, query, is_error=verdict.decision in ("BLOCK", "ERROR"))

        sec = {
            "decision": verdict.decision, "risk_tier": verdict.risk_tier, "score": verdict.score,
            "rule_score": verdict.rule_score, "ml_score": verdict.ml_score,
            "explanations": verdict.explanations, "limit_violations": verdict.limit_violations,
            "latency_ms": round(verdict.latency_ms, 3),
        }
        status, payload, enforced, up_status = 200, None, "forwarded", None
        headers = {"X-Sentinel-Decision": verdict.decision}
        # Shadow (report-only) mode: the real decision is computed and recorded, but not enforced.
        shadow = (self.settings.gateway.enforcement == "shadow" and verdict.decision in ("BLOCK", "THROTTLE")
                  and not _protects_gateway(verdict.limit_violations))
        if shadow:
            sec["shadow"] = True
            headers["X-Sentinel-Shadow"] = "true"

        if verdict.decision == "ERROR":
            status, enforced = 400, "rejected"
            payload = {"data": None, "errors": [{"message": verdict.error or "Invalid GraphQL operation"}]}
        elif verdict.decision == "BLOCK" and not shadow:
            status, enforced = 403, "blocked"
            payload = {"data": None, "errors": [{"message": "Operation blocked by security policy"}]}
        else:
            if verdict.decision == "THROTTLE" and not shadow:
                ok, retry = self.risky_limiter.check(client.ip)
                if not ok:
                    status, enforced = 429, "rate_limited"
                    headers["Retry-After"] = str(max(1, int(retry + 0.999)))
                    payload = {"data": None, "errors": [{"message": "Too many high-risk operations; retry later"}]}
            if payload is None:
                status, payload, enforced, up_status = await self._forward(body, client)
                if shadow and enforced == "forwarded":
                    enforced = "shadow"

        sec["enforced"] = enforced
        event = await self._record(client, query, verdict, enforced, up_status, t0)
        sec["event_id"] = event["id"]
        if not isinstance(payload.get("extensions"), dict):
            payload["extensions"] = {}
        payload["extensions"]["security"] = sec
        if enforced == "simulated":
            sec["simulated"] = True
        return GatewayResponse(status, payload, headers)

    async def _finish_unscored(self, query: str, client: ClientInfo, t0: float, retry: float) -> GatewayResponse:
        verdict = Verdict("THROTTLE", None, None, None, None, {}, [], [], None, None, 0.0)
        event = await self._record(client, query, verdict, "rate_limited", None, t0)
        sec = {
            "decision": "THROTTLE", "enforced": "rate_limited", "risk_tier": None, "score": None,
            "rule_score": None, "ml_score": None, "explanations": [], "limit_violations": [],
            "latency_ms": 0.0, "event_id": event["id"],
        }
        payload = {"data": None, "errors": [{"message": "Rate limit exceeded"}], "extensions": {"security": sec}}
        return GatewayResponse(429, payload, {
            "X-Sentinel-Decision": "THROTTLE", "Retry-After": str(max(1, int(retry + 0.999)))})

    async def _forward(self, body: dict, client: ClientInfo):
        g = self.settings.gateway
        if g.mode == "simulation":
            return 200, {"data": {"simulated": True}}, "simulated", None
        if not g.upstream_url or self._client is None:
            return 503, {"data": None, "errors": [{"message": "Upstream GraphQL endpoint is not configured"}]}, \
                "upstream_error", None
        out = {"query": body["query"]}
        if body.get("variables") is not None:
            out["variables"] = body["variables"]
        if body.get("operationName"):
            out["operationName"] = body["operationName"]
        fwd = {k: v for k, v in client.headers.items() if k.lower() in {h.lower() for h in g.forward_headers}}
        try:
            resp = await self._client.post(g.upstream_url, json=out, headers=fwd)
        except httpx.TimeoutException:
            return 504, _error("Upstream timed out"), "upstream_error", None
        except httpx.HTTPError:
            logger.warning("Upstream request failed", exc_info=True)
            return 502, _error("Upstream request failed"), "upstream_error", None
        if resp.status_code >= 500 or len(resp.content) > g.max_upstream_response_bytes:
            return 502, _error("Upstream returned an error"), "upstream_error", resp.status_code
        try:
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except ValueError:
            return 502, _error("Upstream returned an invalid response"), "upstream_error", resp.status_code
        return resp.status_code, data, "forwarded", resp.status_code

    async def _record(self, client: ClientInfo, query: str, v: Verdict, enforced: str,
                      upstream_status: Optional[int], t0: float) -> dict:
        event = {
            "client_id": client.label, "ip": client.ip, "operation_name": v.operation_name,
            "operation_type": v.operation_type, "query": query, "decision": v.decision,
            "enforced": enforced, "risk_tier": v.risk_tier, "score": v.score, "rule_score": v.rule_score,
            "ml_score": v.ml_score, "features": v.features, "explanations": v.explanations,
            "limit_violations": v.limit_violations, "upstream_status": upstream_status,
            "latency_ms": round(v.latency_ms, 3), "total_latency_ms": round(_ms(t0), 3),
        }
        self.metrics.inc("sentinel_requests_total", decision=v.decision, enforced=enforced)
        self.metrics.observe("sentinel_analysis_duration_seconds", v.latency_ms / 1000.0)
        self.metrics.observe("sentinel_request_duration_seconds", event["total_latency_ms"] / 1000.0)
        for violation in v.limit_violations:
            self.metrics.inc("sentinel_hard_limit_violations_total", limit=re.split(r"[<>]", violation)[0])
        try:
            stored = await asyncio.to_thread(self.store.add, event)
        except Exception:  # noqa: BLE001 - auditing must not take the gateway down
            logger.error("Failed to persist event", exc_info=True)
            return {"id": "unpersisted"}
        self.alerts.submit(stored)
        return stored


def _protects_gateway(violations: List[str]) -> bool:
    """Violations that guard the gateway's own parser; they are enforced even in shadow mode."""
    return any(v == "parse_budget_exceeded" or v.startswith(("query_length", "token_count")) for v in violations)


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _error(message: str, decision: str = "ERROR", enforced: str = "upstream_error") -> Dict[str, Any]:
    return {"data": None, "errors": [{"message": message}],
            "extensions": {"security": {"decision": decision, "enforced": enforced}}}


def _validate_body(body: Any) -> Optional[str]:
    if isinstance(body, list):
        return "Batched (array) requests are not supported; send one operation per request"
    if not isinstance(body, dict):
        return "Request body must be a JSON object"
    q = body.get("query")
    if not isinstance(q, str) or not q.strip():
        return "A non-empty 'query' string is required"
    if body.get("variables") is not None and not isinstance(body["variables"], dict):
        return "'variables' must be an object"
    if body.get("operationName") is not None and not isinstance(body["operationName"], str):
        return "'operationName' must be a string"
    return None
