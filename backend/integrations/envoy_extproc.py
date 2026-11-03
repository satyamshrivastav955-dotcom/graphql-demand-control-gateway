"""Envoy external processor (ext_proc) for Sentinel.

Envoy buffers the request body and asks this gRPC service for a verdict before it routes the request. The service runs
the same engine as the HTTP gateway (parsing, schema cost, rules, hard limits, batching, persisted queries):

* ALLOW    -> continue; Envoy forwards the request to the upstream cluster itself.
* BLOCK    -> an immediate 403 (or 400 for malformed operations, 429 when the high-risk quota is used up) with the same
              JSON error body and ``extensions.security`` explanations the gateway returns; the upstream never sees it.
* shadow   -> the decision is computed and logged but the request continues.

The filter should be configured fail-closed (``failure_mode_allow: false``), see ``deploy/envoy/envoy.yaml``.

Run:  python -m backend.integrations.envoy_extproc --port 9001 [--metrics-port 9102]
Needs the optional packages in ``backend/requirements-extproc.txt`` (grpcio, xds-protos).
"""
from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from concurrent import futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Iterator, Optional

import grpc
from envoy.config.core.v3 import base_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2 as pb
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as pb_grpc
from envoy.type.v3 import http_status_pb2

from ..api.gateway import _batch_summary
from ..core.config import Settings, load_settings
from ..core.engine_factory import build_engine
from ..core.features.behavioral_store import BehavioralStore
from ..core.runtime.limiter import SlidingWindowLimiter
from ..core.runtime.metrics import Metrics
from ..core.runtime.telemetry import Telemetry
from ..core.security_engine.scorer import SecurityScorer

logger = logging.getLogger("sentinel.extproc")
MAX_BODY = 1_000_000


class SentinelExtProc(pb_grpc.ExternalProcessorServicer):
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or load_settings()
        self.metrics = Metrics()
        self.telemetry = Telemetry(self.settings.telemetry, self.settings.app.version)
        self.scorer = SecurityScorer(self.settings.security.policy, self.settings.security.introspection)
        self.engine, self.allowlist = build_engine(self.settings, self.scorer)
        t = self.settings.throttle
        self.rate_limiter = SlidingWindowLimiter(t.rate_limit, t.window_seconds, t.max_tracked_clients)
        self.risky_limiter = SlidingWindowLimiter(t.risky_quota, t.window_seconds, t.max_tracked_clients)
        self.behavior = BehavioralStore(window_seconds=t.window_seconds, max_clients=t.max_tracked_clients)

    # -- gRPC ----------------------------------------------------------------------------------------------------
    def Process(self, request_iterator: Iterator[pb.ProcessingRequest], context) -> Iterator[pb.ProcessingResponse]:
        headers: Dict[str, str] = {}
        for req in request_iterator:
            kind = req.WhichOneof("request")
            if kind == "request_headers":
                headers = {h.key.lower(): (h.raw_value.decode("utf-8", "replace") or h.value)
                           for h in req.request_headers.headers.headers}
                # Bodiless requests (GET, health checks) never produce a request_body message and pass through.
                yield pb.ProcessingResponse(request_headers=pb.HeadersResponse())
            elif kind == "request_body":
                yield self._on_body(req.request_body.body, headers)
            else:  # response phases are skipped by the filter's processing_mode; be liberal anyway
                yield pb.ProcessingResponse()

    # -- decision ------------------------------------------------------------------------------------------------
    def _client_ip(self, headers: Dict[str, str]) -> str:
        fwd = headers.get("x-envoy-external-address") or headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() or "unknown"

    def _on_body(self, raw: bytes, headers: Dict[str, str]) -> pb.ProcessingResponse:
        t0 = time.perf_counter()
        ip = self._client_ip(headers)
        if len(raw) > min(self.settings.limits.max_body_bytes, MAX_BODY):
            return self._deny(413, "Request body too large", "BLOCK", {"limit_violations": ["max_body_bytes"]}, ip)
        try:
            body: Any = json.loads(raw or b"null")
        except ValueError:
            return self._deny(400, "Request body is not valid JSON", "ERROR", {}, ip)
        mutated: Optional[bytes] = None
        if self.allowlist is not None:
            body, err, changed = self._resolve_persisted(body)
            if err:
                return self._deny(400, err, "ERROR", {}, ip)
            if changed:
                mutated = json.dumps(body).encode()

        allowed, retry = self.rate_limiter.check(ip)
        if not allowed:
            return self._deny(429, "Rate limit exceeded", "THROTTLE", {}, ip, retry_after=retry)

        is_batch = isinstance(body, list)
        if is_batch:
            if not body or not all(isinstance(b, dict) and isinstance(b.get("query"), str) for b in body):
                return self._deny(400, "A batch needs non-empty 'query' strings", "ERROR", {}, ip)
            verdict = self.engine.evaluate_batch(body, self.behavior.features(ip))
            query = _batch_summary(body)
        elif isinstance(body, dict) and isinstance(body.get("query"), str) and body["query"].strip():
            query = body["query"]
            verdict = self.engine.evaluate(query, body.get("operationName"), body.get("variables"),
                                           self.behavior.features(ip))
        else:
            return self._deny(400, "A non-empty 'query' string is required", "ERROR", {}, ip)
        self.behavior.record(ip, query, is_error=verdict.decision in ("BLOCK", "ERROR"))

        sec = {"decision": verdict.decision, "risk_tier": verdict.risk_tier, "score": verdict.score,
               "rule_score": verdict.rule_score, "ml_score": verdict.ml_score, "explanations": verdict.explanations,
               "limit_violations": verdict.limit_violations, "owasp": verdict.owasp,
               "latency_ms": round(verdict.latency_ms, 3)}
        shadow = self.settings.gateway.enforcement == "shadow" and verdict.decision in ("BLOCK", "THROTTLE")
        enforced = "forwarded"
        response: Optional[pb.ProcessingResponse] = None
        if verdict.decision == "ERROR":
            enforced, response = "rejected", self._immediate(400, verdict.error or "Invalid GraphQL operation", sec)
        elif verdict.decision == "BLOCK" and not shadow:
            enforced, response = "blocked", self._immediate(403, "Operation blocked by security policy", sec)
        elif verdict.decision == "THROTTLE" and not shadow:
            ok, retry = self.risky_limiter.check(ip)
            if not ok:
                enforced = "rate_limited"
                response = self._immediate(429, "Too many high-risk operations; retry later", sec, retry_after=retry)
        if shadow:
            enforced = "shadow"
        self.metrics.inc("sentinel_requests_total", decision=verdict.decision, enforced=enforced)
        self.metrics.observe("sentinel_analysis_duration_seconds", verdict.latency_ms / 1000.0)
        for e in verdict.explanations:
            if e.get("points", 0) > 0 and e.get("rule") != "ml_model":
                self.metrics.inc("sentinel_rule_hits_total", rule=e["rule"], owasp=",".join(e.get("owasp", [])) or "none")
        self.telemetry.decision(verdict, enforced=enforced, client=ip, event_id=None, query=query, upstream_status=None,
                                total_ms=(time.perf_counter() - t0) * 1000, shadow=shadow)
        if response is not None:
            return response
        if mutated is not None:
            return pb.ProcessingResponse(request_body=pb.BodyResponse(response=pb.CommonResponse(
                status=pb.CommonResponse.CONTINUE_AND_REPLACE, body_mutation=pb.BodyMutation(body=mutated))))
        return pb.ProcessingResponse(request_body=pb.BodyResponse())

    def _resolve_persisted(self, body: Any):
        changed = False
        items = body if isinstance(body, list) else [body]
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("extensions"), dict):
                text, err = self.allowlist.resolve(item.get("query"), item["extensions"])  # type: ignore[union-attr]
                if err:
                    return body, err, False
                if not item.get("query") and text:
                    item["query"], changed = text, True
        return body, None, changed

    # -- responses -----------------------------------------------------------------------------------------------
    def _deny(self, status: int, message: str, decision: str, extra: Dict[str, Any], ip: str,
              retry_after: Optional[float] = None) -> pb.ProcessingResponse:
        self.metrics.inc("sentinel_requests_total", decision=decision, enforced="rejected")
        return self._immediate(status, message, {"decision": decision, **extra}, retry_after=retry_after)

    @staticmethod
    def _immediate(status: int, message: str, security: Dict[str, Any], retry_after: Optional[float] = None
                   ) -> pb.ProcessingResponse:
        payload = {"data": None, "errors": [{"message": message}], "extensions": {"security": security}}
        hdrs = [("content-type", "application/json"), ("x-sentinel-decision", str(security.get("decision", "")))]
        if retry_after is not None:
            hdrs.append(("retry-after", str(max(1, int(retry_after + 0.999)))))
        mutation = base_pb2.HeaderValueOption
        return pb.ProcessingResponse(immediate_response=pb.ImmediateResponse(
            status=http_status_pb2.HttpStatus(code=status),
            headers=pb.HeaderMutation(set_headers=[mutation(header=base_pb2.HeaderValue(key=k, raw_value=v.encode()))
                                                   for k, v in hdrs]),
            body=json.dumps(payload).encode(), details=f"sentinel_{str(security.get('decision', '')).lower()}"))


def serve(port: int = 9001, metrics_port: Optional[int] = 9102, settings: Optional[Settings] = None,
          max_workers: int = 16) -> grpc.Server:
    svc = SentinelExtProc(settings)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb_grpc.add_ExternalProcessorServicer_to_server(svc, server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    if metrics_port:
        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib name
                if self.path in ("/metrics", "/health"):
                    body = svc.metrics.render() if self.path == "/metrics" else "ok\n"
                    self.send_response(200)
                    self.send_header("content-type", "text/plain; version=0.0.4")
                    self.end_headers()
                    self.wfile.write(body.encode())
                else:
                    self.send_error(404)

            def log_message(self, *a):
                pass

        httpd = HTTPServer(("0.0.0.0", metrics_port), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info("Sentinel ext_proc listening on :%s (metrics :%s)", port, metrics_port)
    server.sentinel_service = svc  # type: ignore[attr-defined]
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=9001)
    ap.add_argument("--metrics-port", type=int, default=9102)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    serve(a.port, a.metrics_port).wait_for_termination()


if __name__ == "__main__":
    main()
