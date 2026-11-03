"""OpenTelemetry traces and metrics plus structured (JSON) decision logs.

Everything is optional and off by default:

* ``telemetry.decision_log: json``  one JSON line per decision on the ``sentinel.decision`` logger (stdout), carrying
  the decision, the rules that fired with their OWASP categories, latency and the trace id. It never contains query text
  or variables, only a SHA-256 of the query.
* ``telemetry.enabled: true`` with ``telemetry.otlp_endpoint`` (or the standard ``OTEL_EXPORTER_OTLP_ENDPOINT``) exports
  spans and metrics over OTLP/HTTP. Install the extra packages from ``backend/requirements-otel.txt``. Incoming W3C
  ``traceparent`` headers are honoured and forwarded to the upstream, so a Sentinel span sits inside the caller's trace.

Span tree per request::

    sentinel.request            decision, risk tier, score, OWASP categories, enforced action
      sentinel.evaluate         parse + cost + score + limits
      sentinel.forward          the upstream call (absent when blocked)
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import sys
from typing import Any, Dict, Iterator, Mapping, Optional

from ..config import TelemetrySettings

logger = logging.getLogger(__name__)
decision_logger = logging.getLogger("sentinel.decision")


class _NoopSpan:
    def set_attribute(self, *_a, **_k) -> None: ...
    def set_attributes(self, *_a, **_k) -> None: ...
    def record_exception(self, *_a, **_k) -> None: ...


NOOP = _NoopSpan()


class Telemetry:
    def __init__(self, cfg: Optional[TelemetrySettings] = None, version: str = "dev"):
        self.cfg = cfg or TelemetrySettings()
        self.otel = False
        self._tracer: Any = None
        self._propagate: Any = None
        self._instruments: Dict[str, Any] = {}
        if self.cfg.decision_log == "json" and not decision_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            decision_logger.addHandler(handler)
            decision_logger.setLevel(logging.INFO)
            decision_logger.propagate = False
        if self.cfg.enabled:
            self._init_otel(version)

    # -- setup -----------------------------------------------------------------------------------------------------
    def _init_otel(self, version: str) -> None:
        try:
            from opentelemetry import propagate, trace
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            logger.warning("telemetry.enabled is set but OpenTelemetry is not installed "
                           "(pip install -r backend/requirements-otel.txt); tracing is off")
            return
        resource = Resource.create({"service.name": self.cfg.service_name, "service.version": version})
        endpoint = self.cfg.otlp_endpoint
        tp = TracerProvider(resource=resource)
        readers = []
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            base = endpoint.rstrip("/")
            tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces")))
            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"),
                                                         export_interval_millis=10_000))
        mp = MeterProvider(resource=resource, metric_readers=readers)
        # Use the SDK providers directly (not the process-global ones) so tests and embedders can run several.
        self._tracer = tp.get_tracer("graphql-sentinel", version)
        meter = mp.get_meter("graphql-sentinel", version)
        self._tp, self._mp = tp, mp
        self._propagate = propagate
        self._trace = trace
        self._instruments = {
            "requests": meter.create_counter("sentinel.requests", description="Operations handled"),
            "rules": meter.create_counter("sentinel.rule.hits", description="Rule hits by rule and OWASP category"),
            "analysis": meter.create_histogram("sentinel.analysis.duration", unit="ms",
                                               description="Parse, cost, score and decide time"),
            "request": meter.create_histogram("sentinel.request.duration", unit="ms",
                                              description="Total request time including the upstream"),
            "cost": meter.create_histogram("sentinel.schema.cost", description="Estimated schema cost per operation"),
        }
        self.otel = True

    def shutdown(self) -> None:
        if self.otel:
            with contextlib.suppress(Exception):
                self._tp.shutdown()
                self._mp.shutdown()

    # -- tracing -----------------------------------------------------------------------------------------------------
    @contextlib.contextmanager
    def span(self, name: str, headers: Optional[Mapping[str, str]] = None, **attributes) -> Iterator[Any]:
        if not self.otel:
            yield NOOP
            return
        ctx = self._propagate.extract(dict(headers)) if headers else None
        with self._tracer.start_as_current_span(name, context=ctx) as sp:
            for k, v in attributes.items():
                sp.set_attribute(k, v)
            yield sp

    def inject(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Add W3C trace-context headers for the current span (no-op when tracing is off)."""
        if self.otel:
            self._propagate.inject(headers)
        return headers

    def ids(self) -> Dict[str, str]:
        if not self.otel:
            return {}
        sc = self._trace.get_current_span().get_span_context()
        if not sc.is_valid:
            return {}
        return {"trace_id": format(sc.trace_id, "032x"), "span_id": format(sc.span_id, "016x")}

    # -- decisions -----------------------------------------------------------------------------------------------------
    def decision(self, verdict: Any, *, enforced: str, client: str, event_id: Optional[str], query: str,
                 upstream_status: Optional[int], total_ms: float, shadow: bool = False) -> None:
        owasp = list(getattr(verdict, "owasp", []) or [])
        rules = [{"rule": e["rule"], "points": e["points"], "owasp": e.get("owasp", [])}
                 for e in (verdict.explanations or []) if e.get("rule") != "ml_model" or e.get("points")]
        if self.cfg.decision_log == "json":
            record = {
                "event": "decision", "ts": _now(), "event_id": event_id, "decision": verdict.decision,
                "enforced": enforced, "shadow": shadow, "risk_tier": verdict.risk_tier, "score": verdict.score,
                "rule_score": verdict.rule_score, "ml_score": verdict.ml_score, "owasp": owasp, "rules": rules,
                "limit_violations": verdict.limit_violations, "operation_name": verdict.operation_name,
                "operation_type": verdict.operation_type, "client": client,
                "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
                "cost": (verdict.cost or {}).get("total") if verdict.cost else None,
                "analysis_ms": round(verdict.latency_ms, 3), "total_ms": round(total_ms, 3),
                "upstream_status": upstream_status, **self.ids(),
            }
            decision_logger.info(json.dumps(record, separators=(",", ":"), default=str))
        if not self.otel:
            return
        ins = self._instruments
        ins["requests"].add(1, {"decision": verdict.decision, "enforced": enforced})
        for e in verdict.explanations or []:
            if e.get("rule") and e.get("points", 0) > 0 or str(e.get("rule", "")).startswith("hard"):
                ins["rules"].add(1, {"rule": e["rule"], "owasp": ",".join(e.get("owasp", []))})
        ins["analysis"].record(verdict.latency_ms)
        ins["request"].record(total_ms)
        if verdict.cost:
            ins["cost"].record(verdict.cost["total"])

    def annotate(self, span: Any, verdict: Any, enforced: str) -> None:
        span.set_attribute("sentinel.decision", verdict.decision)
        span.set_attribute("sentinel.enforced", enforced)
        if verdict.risk_tier:
            span.set_attribute("sentinel.risk_tier", verdict.risk_tier)
        if verdict.score is not None:
            span.set_attribute("sentinel.score", float(verdict.score))
        if getattr(verdict, "owasp", None):
            span.set_attribute("sentinel.owasp", list(verdict.owasp))
        fired = [e["rule"] for e in verdict.explanations or [] if e.get("points", 0) > 0]
        if fired:
            span.set_attribute("sentinel.rules", fired[:12])
        if verdict.limit_violations:
            span.set_attribute("sentinel.limit_violations", list(verdict.limit_violations))
        if verdict.cost:
            span.set_attribute("sentinel.schema_cost", int(verdict.cost["total"]))


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat(timespec="milliseconds")
