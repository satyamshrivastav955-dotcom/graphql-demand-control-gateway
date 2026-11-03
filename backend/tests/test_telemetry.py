"""Structured decision logs, OpenTelemetry spans/metrics, and the OWASP fields in API responses."""
import json

import pytest

from .conftest import deep_query


def _decisions(capsys):
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.startswith('{"event":"decision"')]


def test_decision_log_is_one_json_line_per_decision_and_never_contains_query_text(make_harness, capsys):
    h = make_harness({"telemetry": {"decision_log": "json"}})
    h.post("{ users(first: 1) { name } }")
    h.post(deep_query(20))
    lines = _decisions(capsys)
    assert [d["decision"] for d in lines] == ["ALLOW", "BLOCK"]
    block = lines[1]
    assert block["owasp"] and "API4" in block["owasp"] and block["limit_violations"]
    assert {"event_id", "risk_tier", "score", "analysis_ms", "total_ms", "query_sha256", "rules"} <= block.keys()
    assert "users" not in json.dumps(lines)  # no query text


def test_decision_log_is_off_by_default(make_harness, capsys):
    h = make_harness()
    h.post("{ users(first: 1) { name } }")
    assert _decisions(capsys) == []


def test_responses_and_events_carry_owasp_mapping(make_harness):
    h = make_harness()
    sec = h.post(deep_query(20)).json()["extensions"]["security"]
    assert all("owasp" in e and "attack_class" in e for e in sec["explanations"] if e["rule"] != "ml_model")
    assert any("API4" in e.get("owasp", []) for e in sec["explanations"])
    assert h.events()["items"][0]["explanations"]


def test_rule_hits_are_exported_as_prometheus_counters(make_harness):
    h = make_harness()
    h.post(deep_query(20))
    text = h.client.get("/metrics").text
    assert 'sentinel_rule_hits_total{owasp="API4",rule="depth"}' in text


def test_rules_endpoint_lists_the_catalogue(make_harness):
    r = make_harness().client.get("/api/rules")
    assert r.status_code == 200
    rules = {x["id"]: x for x in r.json()["rules"]}
    assert rules["depth"]["owasp"] == ["API4"] and "API4" in r.json()["owasp"]


@pytest.fixture
def otel():
    try:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        return SimpleSpanProcessor, InMemorySpanExporter
    except Exception as exc:
        pytest.skip(f"opentelemetry sdk import failed: {exc}")


def test_spans_are_emitted_with_decision_attributes_and_join_the_callers_trace(make_harness, otel):
    SimpleSpanProcessor, InMemorySpanExporter = otel
    h = make_harness({"telemetry": {"enabled": True}})
    tel = h.gateway.telemetry
    assert tel.otel
    exporter = InMemorySpanExporter()
    tel._tp.add_span_processor(SimpleSpanProcessor(exporter))
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    h.client.post("/graphql-proxy", json={"query": deep_query(20)},
                  headers={"traceparent": f"00-{trace_id}-b7ad6b7169203331-01"})
    h.client.post("/graphql-proxy", json={"query": "{ users(first: 1) { name } }"})
    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert names.count("sentinel.request") == 2 and "sentinel.evaluate" in names and "sentinel.forward" in names
    blocked = next(s for s in spans if s.name == "sentinel.request" and s.attributes.get("sentinel.decision") == "BLOCK")
    assert format(blocked.context.trace_id, "032x") == trace_id
    assert "API4" in blocked.attributes["sentinel.owasp"]
    # the forwarded request carries trace context
    assert any(c.headers.get("traceparent") for c in h.calls)


def test_telemetry_degrades_gracefully_when_otel_is_missing(make_harness, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("opentelemetry"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    h = make_harness({"telemetry": {"enabled": True}})
    assert h.gateway.telemetry.otel is False
    assert h.post("{ users(first: 1) { name } }").status_code == 200
