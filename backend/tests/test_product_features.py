"""Shadow mode, Prometheus metrics, webhook alerts, event export and batch rejection."""
import csv
import io
import json
import time

import httpx
import pytest

from backend.core.runtime.metrics import Metrics

from .conftest import TOKEN, alias_query, deep_query

BENIGN = "{ users(first: 1) { name } }"
HIGH_RISK = deep_query(14)
OVER_LIMIT = deep_query(16)
WEBHOOK = "https://hooks.example.test/services/T000/B000/secret-path"


def sec(r):
    return r.json()["extensions"]["security"]


def wait_for(predicate, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# ---- shadow (report-only) mode ---------------------------------------------------------------------------
def shadow(make_harness, **kw):
    return make_harness({"gateway": {"enforcement": "shadow"}}, **kw)


def test_shadow_mode_records_the_real_decision_but_forwards(make_harness):
    h = shadow(make_harness)
    r = h.post(OVER_LIMIT)  # would be a hard BLOCK
    assert r.status_code == 200 and len(h.calls) == 1
    s = sec(r)
    assert s["decision"] == "BLOCK" and s["enforced"] == "shadow" and s["shadow"] is True
    assert r.headers["x-sentinel-decision"] == "BLOCK" and r.headers["x-sentinel-shadow"] == "true"
    ev = h.events(decision="BLOCK")["items"][0]
    assert ev["enforced"] == "shadow" and ev["upstream_status"] == 200 and ev["limit_violations"]


def test_shadow_mode_never_throttles(make_harness):
    h = make_harness({"gateway": {"enforcement": "shadow"}, "throttle": {"risky_quota": 1}})
    codes = [h.post(HIGH_RISK).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 200] and len(h.calls) == 4


def test_shadow_mode_leaves_normal_traffic_and_non_decisions_alone(make_harness):
    h = shadow(make_harness)
    ok = h.post(BENIGN)
    assert ok.status_code == 200 and sec(ok)["enforced"] == "forwarded" and "shadow" not in sec(ok)
    assert h.post("query {").status_code == 400  # syntax errors are still rejected


def test_shadow_mode_still_protects_the_gateway_parser(make_harness):
    h = make_harness({"gateway": {"enforcement": "shadow"}, "limits": {"max_query_length": 200}})
    r = h.post("{ " + "name " * 100 + "}")
    assert r.status_code == 403 and h.calls == []  # query_length guards the parser even in shadow
    huge = make_harness({"gateway": {"enforcement": "shadow"}, "limits": {"max_tokens": 100_000, "max_query_length": 100_000}})
    r2 = huge.post("{ a " * 3000 + "}" * 3000)
    assert r2.status_code == 403 and huge.calls == []


def test_shadow_mode_still_applies_the_per_ip_rate_limit(make_harness):
    h = make_harness({"gateway": {"enforcement": "shadow"}, "throttle": {"rate_limit": 2}})
    assert [h.post(BENIGN).status_code for _ in range(3)] == [200, 200, 429]


def test_config_reports_enforcement_mode(make_harness):
    assert shadow(make_harness).client.get("/api/config").json()["enforcement"] == "shadow"
    assert make_harness().client.get("/api/config").json()["enforcement"] == "enforce"


# ---- batch requests ---------------------------------------------------------------------------------------
def test_batched_array_requests_are_rejected_with_a_clear_message(make_harness):
    h = make_harness()
    r = h.client.post("/graphql-proxy", json=[{"query": BENIGN}, {"query": BENIGN}])
    assert r.status_code == 400 and "Batched" in r.json()["errors"][0]["message"] and h.calls == []


# ---- Prometheus metrics -------------------------------------------------------------------------------------
def test_metrics_endpoint_requires_the_token(make_harness):
    h = make_harness()
    h.client.headers.pop("Authorization")
    assert h.client.get("/metrics").status_code == 401


def test_metrics_reflect_traffic(make_harness):
    h = make_harness()
    h.post(BENIGN)
    h.post(OVER_LIMIT)
    h.post(alias_query(60))
    text = h.client.get("/metrics").text
    assert 'sentinel_requests_total{decision="ALLOW",enforced="forwarded"} 1' in text
    assert 'sentinel_requests_total{decision="BLOCK",enforced="blocked"} 2' in text
    assert 'sentinel_hard_limit_violations_total{limit="max_depth"} 1' in text
    assert 'sentinel_hard_limit_violations_total{limit="alias_count"} 1' in text
    assert "sentinel_analysis_duration_seconds_count 3" in text and 'le="+Inf"} 3' in text
    assert "sentinel_model_loaded" in text and 'sentinel_info{' in text and 'enforcement="enforce"' in text
    assert TOKEN not in text
    assert h.client.get("/metrics").headers["content-type"].startswith("text/plain")


def test_metrics_histogram_is_cumulative_and_labels_are_escaped():
    m = Metrics()
    for v in (0.0005, 0.003, 0.2, 20):
        m.observe("sentinel_analysis_duration_seconds", v)
    m.inc("sentinel_requests_total", decision='B"L\nOCK', enforced="x\\y")
    text = m.render()
    counts = [int(line.rsplit(" ", 1)[1]) for line in text.splitlines() if line.startswith("sentinel_analysis_duration_seconds_bucket")]
    assert counts == sorted(counts) and counts[-1] == 4
    assert 'decision="B\\"L\\nOCK"' in text and 'enforced="x\\\\y"' in text


# ---- webhook alerts -----------------------------------------------------------------------------------------
def alerting(make_harness, **alerts):
    return make_harness({"alerts": {"webhook_url": WEBHOOK, **alerts}})


def test_blocked_operation_sends_one_alert_without_query_text(make_harness):
    h = alerting(make_harness)
    h.post(OVER_LIMIT)
    assert wait_for(lambda: len(h.alert_calls) == 1)
    req = h.alert_calls[0]
    assert str(req.url) == WEBHOOK
    body = json.loads(req.content)
    assert "BLOCK" in body["text"] and body["event"]["decision"] == "BLOCK" and "hard_limit" in body["event"]["rules"]
    assert "query" not in body["event"]
    h.post(BENIGN)
    time.sleep(0.15)
    assert len(h.alert_calls) == 1  # allowed traffic does not alert


def test_alert_query_text_is_opt_in_and_redacted(make_harness):
    h = alerting(make_harness, include_query=True)
    flood = "mutation { " + " ".join(f'a{i}: login(email: "x@y.z", password: "hunter2") {{ token }}' for i in range(60)) + " }"
    h.post(flood)  # 60 aliases: blocked, and the query contains a credential literal
    assert wait_for(lambda: len(h.alert_calls) == 1)
    payload = json.loads(h.alert_calls[0].content)
    assert "query" in payload["event"] and "[REDACTED]" in payload["event"]["query"]
    assert "hunter2" not in json.dumps(payload)


def test_throttle_alerts_only_when_configured_and_rate_limit_noise_is_ignored(make_harness):
    quiet = alerting(make_harness)
    quiet.post(HIGH_RISK)
    time.sleep(0.2)
    assert quiet.alert_calls == []
    loud = alerting(make_harness, min_decision="THROTTLE")
    loud.post(HIGH_RISK)
    assert wait_for(lambda: len(loud.alert_calls) == 1)
    flood = make_harness({"alerts": {"webhook_url": WEBHOOK, "min_decision": "THROTTLE"}, "throttle": {"rate_limit": 1}})
    flood.post(BENIGN)
    flood.post(BENIGN)  # 429 rate_limited
    time.sleep(0.2)
    assert flood.alert_calls == []


def test_alert_rate_is_capped_and_overflow_is_counted(make_harness):
    h = alerting(make_harness, max_per_minute=2)
    for _ in range(6):
        h.post(OVER_LIMIT)
    assert wait_for(lambda: len(h.alert_calls) == 2)
    time.sleep(0.2)
    assert len(h.alert_calls) == 2
    text = h.client.get("/metrics").text
    assert 'sentinel_alerts_total{result="dropped"} 4' in text and 'sentinel_alerts_total{result="sent"} 2' in text


def test_failing_webhook_never_affects_the_request_and_never_logs_the_url(make_harness, caplog):
    def boom(request):
        raise httpx.ConnectError("cannot reach " + str(request.url))
    h = make_harness({"alerts": {"webhook_url": WEBHOOK}}, alert_handler=boom)
    with caplog.at_level("DEBUG"):
        assert h.post(OVER_LIMIT).status_code == 403
        assert wait_for(lambda: 'sentinel_alerts_total{result="failed"} 1' in h.client.get("/metrics").text)
    assert "secret-path" not in caplog.text


def test_webhook_url_is_validated_and_never_exposed(make_harness):
    from pydantic import ValidationError

    from backend.core.config import AlertSettings
    with pytest.raises(ValidationError):
        AlertSettings(webhook_url="ftp://nope")
    h = alerting(make_harness)
    cfg = h.client.get("/api/config").json()
    assert cfg["alerts_configured"] is True and "secret-path" not in json.dumps(cfg)


# ---- events export -------------------------------------------------------------------------------------------
def test_export_requires_auth_and_returns_csv(make_harness):
    h = make_harness()
    h.post(BENIGN)
    h.post(OVER_LIMIT)
    r = h.client.get("/api/events/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 2 and {x["decision"] for x in rows} == {"ALLOW", "BLOCK"}
    assert "max_depth" in next(x for x in rows if x["decision"] == "BLOCK")["limit_violations"]
    h.client.headers.pop("Authorization")
    assert h.client.get("/api/events/export").status_code == 401


def test_export_filters_json_and_formula_injection(make_harness):
    h = make_harness()
    h.post(BENIGN)
    h.post(OVER_LIMIT)
    only_block = h.client.get("/api/events/export", params={"format": "json", "decision": "BLOCK"}).json()
    assert only_block["count"] == 1 and only_block["events"][0]["decision"] == "BLOCK"
    h.store.add({"decision": "ALLOW", "query": "=HYPERLINK(\"http://evil\")", "operation_name": "@cmd", "ip": "-1"})
    text = h.client.get("/api/events/export").text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert any(x["query"].startswith("'=") for x in rows) and any(x["operation_name"] == "'@cmd" for x in rows)
    assert all(not x["query"].startswith("=") for x in rows)
    assert h.client.get("/api/events/export", params={"limit": 1}).text.count("\n") == 2  # header + 1 row
