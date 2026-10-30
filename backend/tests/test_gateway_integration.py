import json

import httpx
import pytest

from backend.core.runtime.events import EventStore, redact_query

from .conftest import alias_query, deep_query

BENIGN = "query Q($id: ID!) { user(id: $id) { name } }"
HIGH_RISK = deep_query(14)       # scores in the HIGH_RISK tier, within hard limits
OVER_LIMIT = deep_query(16)      # exceeds max_depth=15 -> hard BLOCK


def sec(resp):
    return resp.json()["extensions"]["security"]


# ---- forwarding ---------------------------------------------------------------------------
def test_allowed_query_reaches_upstream_and_returns_its_real_response(make_harness):
    h = make_harness(handler=lambda r: httpx.Response(200, json={"data": {"user": {"name": "Ada"}}}))
    r = h.post(BENIGN, variables={"id": "7"}, operationName="Q")
    assert r.status_code == 200
    assert r.json()["data"] == {"user": {"name": "Ada"}}
    assert sec(r)["decision"] == "ALLOW" and sec(r)["enforced"] == "forwarded"
    assert r.headers["x-sentinel-decision"] == "ALLOW"
    assert len(h.calls) == 1
    sent = json.loads(h.calls[0].content)
    assert sent == {"query": BENIGN, "variables": {"id": "7"}, "operationName": "Q"}
    assert str(h.calls[0].url) == "http://upstream.test/graphql"


def test_upstream_graphql_errors_pass_through(make_harness):
    h = make_harness(handler=lambda r: httpx.Response(200, json={"data": None, "errors": [{"message": "nope"}]}))
    r = h.post(BENIGN)
    assert r.json()["errors"] == [{"message": "nope"}] and sec(r)["decision"] == "ALLOW"


def test_only_allow_listed_headers_are_forwarded(make_harness):
    h = make_harness()
    h.post(BENIGN, headers={"Authorization": "Bearer t0k", "Cookie": "session=abc", "X-Request-ID": "r1"})
    sent = h.calls[0].headers
    assert sent["authorization"] == "Bearer t0k" and sent["x-request-id"] == "r1"
    assert "cookie" not in sent


# ---- blocking --------------------------------------------------------------------------------
@pytest.mark.parametrize("query,violation", [
    (OVER_LIMIT, "max_depth"), (alias_query(60), "alias_count"),
    ("{ a { ...A } } fragment A on T { b { ...A } }", "fragment_cycle"),
])
def test_blocked_queries_never_reach_upstream(make_harness, query, violation):
    h = make_harness()
    r = h.post(query)
    assert r.status_code == 403
    assert sec(r)["decision"] == "BLOCK" and sec(r)["enforced"] == "blocked"
    assert any(violation in v for v in sec(r)["limit_violations"])
    assert r.json()["data"] is None
    assert h.calls == []


def test_pathological_nesting_is_blocked_not_a_server_error(make_harness):
    h = make_harness({"limits": {"max_tokens": 100_000, "max_query_length": 100_000}})
    r = h.post("{ a " * 3000 + "}" * 3000)
    assert r.status_code == 403 and sec(r)["limit_violations"] and h.calls == []


def test_introspection_block_mode(make_harness):
    h = make_harness({"security": {"introspection": "block"}})
    r = h.post("{ __schema { types { name } } }")
    assert r.status_code == 403 and "introspection_disabled" in sec(r)["limit_violations"]
    assert h.calls == []


def test_introspection_flag_mode_alerts_but_allows(make_harness):
    h = make_harness()
    r = h.post("{ __schema { types { name } } }")
    assert r.status_code == 200 and sec(r)["risk_tier"] == "MEDIUM_RISK" and len(h.calls) == 1


def test_legitimate_nested_query_is_not_blocked(make_harness):
    h = make_harness()
    r = h.post("{ user(id: 1) { posts(first: 5) { comments(first: 5) { author { name } } } } }")
    assert r.status_code == 200 and sec(r)["decision"] == "ALLOW"


# ---- throttling ------------------------------------------------------------------------------
def test_throttle_tier_is_rate_limited_after_quota(make_harness):
    h = make_harness({"throttle": {"risky_quota": 2}})
    first, second, third = (h.post(HIGH_RISK) for _ in range(3))
    for r in (first, second):
        assert r.status_code == 200 and sec(r)["decision"] == "THROTTLE" and sec(r)["enforced"] == "forwarded"
    assert third.status_code == 429 and sec(third)["enforced"] == "rate_limited"
    assert int(third.headers["retry-after"]) >= 1
    assert len(h.calls) == 2
    assert h.post(BENIGN).status_code == 200  # normal traffic from the same client is unaffected


def test_global_rate_limit_applies_to_all_traffic(make_harness):
    h = make_harness({"throttle": {"rate_limit": 3}})
    codes = [h.post(BENIGN).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert len(h.calls) == 3
    limited = h.events(decision="THROTTLE")["items"]
    assert limited and limited[0]["enforced"] == "rate_limited"


def test_spoofed_client_id_does_not_evade_rate_limit(make_harness):
    h = make_harness({"throttle": {"rate_limit": 2}})
    codes = [h.post(BENIGN, headers={"X-Client-ID": f"fresh-{i}"}).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429]


# ---- upstream failure handling -----------------------------------------------------------------
@pytest.mark.parametrize("handler,status", [
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("secret-host timed out")), 504),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("connect to 10.0.0.5 refused")), 502),
    (lambda r: httpx.Response(500, text="Traceback: db password=hunter2"), 502),
    (lambda r: httpx.Response(200, text="<html>not json</html>"), 502),
    (lambda r: httpx.Response(200, json=["not", "an", "object"]), 502),
])
def test_upstream_failures_are_safe(make_harness, handler, status):
    h = make_harness(handler=handler)
    r = h.post(BENIGN)
    assert r.status_code == status
    body = json.dumps(r.json())
    for leak in ("hunter2", "10.0.0.5", "secret-host", "Traceback"):
        assert leak not in body
    assert r.json()["data"] is None and sec(r)["enforced"] == "upstream_error"


def test_missing_upstream_is_an_error_not_a_fake_success(make_harness):
    h = make_harness(upstream=None)
    r = h.post(BENIGN)
    assert r.status_code == 503 and r.json()["data"] is None
    assert "simulated" not in json.dumps(r.json())
    assert h.calls == []


def test_simulation_mode_is_explicit_and_labelled(make_harness):
    h = make_harness({"gateway": {"mode": "simulation"}}, upstream=None)
    r = h.post(BENIGN)
    assert r.status_code == 200 and r.json()["data"] == {"simulated": True}
    assert sec(r)["simulated"] is True and sec(r)["enforced"] == "simulated"
    assert h.calls == []


# ---- input validation ----------------------------------------------------------------------------
@pytest.mark.parametrize("body", [{}, {"query": "   "}, {"query": 5}, {"query": "{a}", "variables": "x"},
                                  {"query": "{a}", "operationName": 3}, [1, 2], "str"])
def test_invalid_bodies_are_400(make_harness, body):
    h = make_harness()
    r = h.client.post("/graphql-proxy", json=body)
    assert r.status_code == 400 and h.calls == []


def test_invalid_json_and_oversized_bodies(make_harness):
    h = make_harness({"limits": {"max_body_bytes": 1000}})
    assert h.client.post("/graphql-proxy", content=b"{not json").status_code == 400
    assert h.client.post("/graphql-proxy", content=b"x" * 5000).status_code == 413
    assert h.calls == []


def test_syntax_error_is_400_and_recorded(make_harness):
    h = make_harness()
    r = h.post("query {")
    assert r.status_code == 400 and sec(r)["decision"] == "ERROR"
    assert h.events(decision="ERROR")["total"] == 1 and h.calls == []


def test_query_longer_than_limit_is_blocked(make_harness):
    h = make_harness({"limits": {"max_query_length": 200}})
    assert h.post("{ " + "name " * 100 + "}").status_code == 403


# ---- audit events, API --------------------------------------------------------------------------
def test_events_are_recorded_and_retrievable(make_harness):
    h = make_harness()
    event_id = sec(h.post(BENIGN, variables={"id": "secret-var-value"}))["event_id"]
    ev = h.client.get(f"/api/events/{event_id}").json()
    assert ev["decision"] == "ALLOW" and ev["query"] == BENIGN and ev["upstream_status"] == 200
    assert ev["features"]["max_depth"] == 2 and ev["timestamp"].endswith("Z")
    assert "secret-var-value" not in json.dumps(ev)  # variables are never persisted
    assert h.client.get("/api/events/does-not-exist").status_code == 404


def test_event_list_filters_search_and_sorting(make_harness):
    h = make_harness()
    h.post(BENIGN)
    h.post(OVER_LIMIT)
    h.post(HIGH_RISK)
    assert h.events()["total"] == 3
    assert h.events(decision="block")["total"] == 1
    assert h.events(tier="HIGH_RISK")["total"] == 1
    assert h.events(q="user(id")["total"] == 1
    by_score = h.events(sort="score", order="desc")["items"]
    assert [e["score"] for e in by_score] == sorted((e["score"] for e in by_score), reverse=True)
    assert len(h.events(limit=2)["items"]) == 2 and h.events(limit=2, offset=2)["items"]


def test_credentials_in_queries_are_redacted_before_storage(make_harness):
    h = make_harness()
    h.post('mutation { login(email: "a@b.c", password: "hunter2") { token } }')
    stored = h.events()["items"][0]["query"]
    assert "hunter2" not in stored and "[REDACTED]" in stored and "a@b.c" in stored
    assert redact_query('x(apiKey: "k-123", name: "ok")') == 'x(apiKey: "[REDACTED]", name: "ok")'


def test_metrics_reflect_real_events(make_harness):
    h = make_harness()
    h.post(BENIGN); h.post(BENIGN); h.post(OVER_LIMIT); h.post("query {")
    m = h.client.get("/api/metrics").json()
    assert m["total_queries"] == 4 and m["allowed_count"] == 2 and m["blocked_count"] == 1 and m["error_count"] == 1
    assert m["block_rate"] == 0.25 and m["active_clients"] == 1
    assert m["tier_distribution"]["CRITICAL"] == 1
    assert any(s["rule"] == "hard_limit" for s in m["top_signals"])
    assert m["recent_suspicious"] and m["avg_latency_ms"] >= 0


def test_analyze_endpoint_is_a_dry_run(make_harness):
    h = make_harness()
    r = h.client.post("/api/analyze", json={"query": HIGH_RISK})
    body = r.json()
    assert r.status_code == 200 and body["decision"] == "THROTTLE" and body["would_forward"] is True
    assert body["features"]["max_depth"] == 14 and body["explanations"]
    assert h.calls == [] and h.events()["total"] == 0
    assert h.client.post("/api/analyze", json={"query": "query {"}).status_code == 400
    assert h.client.post("/api/analyze", json={"query": OVER_LIMIT}).json()["would_forward"] is False


def test_config_endpoint_exposes_no_secrets(make_harness):
    h = make_harness(upstream="http://svc-user:p4ssw0rd@internal.example:8080/graphql")
    body = h.client.get("/api/config").json()
    assert body["upstream_host"] == "internal.example:8080"
    assert "p4ssw0rd" not in json.dumps(body) and "svc-user" not in json.dumps(body)
    assert body["limits"]["max_depth"] == 15 and body["tier_actions"]["CRITICAL"] == "BLOCK"


def test_health_and_ready(make_harness):
    h = make_harness()
    assert h.client.get("/api/health").json() == {"status": "ok"}
    ready = h.client.get("/api/ready").json()
    assert ready["checks"]["store"] is True and ready["checks"]["upstream"] == "ok"
    down = make_harness(handler=lambda r: httpx.Response(503))
    assert down.client.get("/api/ready").json()["status"] == "degraded"


def test_evaluation_endpoint_reports_availability(make_harness, tmp_path, monkeypatch):
    from backend.api import routes
    h = make_harness()
    monkeypatch.setattr(routes, "EVALUATION_FILE", tmp_path / "missing.json")
    assert h.client.get("/api/evaluation").json() == {"available": False}
    f = tmp_path / "e.json"
    f.write_text(json.dumps({"seed": 1, "methods": []}))
    monkeypatch.setattr(routes, "EVALUATION_FILE", f)
    assert h.client.get("/api/evaluation").json()["available"] is True


def test_persistence_failure_does_not_break_the_response(make_harness, monkeypatch):
    h = make_harness()
    monkeypatch.setattr(h.store, "add", lambda e: (_ for _ in ()).throw(RuntimeError("disk full")))
    r = h.post(BENIGN)
    assert r.status_code == 200 and sec(r)["event_id"] == "unpersisted"


def test_cors_allows_only_configured_origins(make_harness):
    h = make_harness({"cors": {"allow_origins": ["https://dash.test"]}})
    ok = h.client.options("/graphql-proxy", headers={"Origin": "https://dash.test", "Access-Control-Request-Method": "POST"})
    bad = h.client.options("/graphql-proxy", headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://dash.test"
    assert "access-control-allow-origin" not in bad.headers


# ---- event store ----------------------------------------------------------------------------------
def test_event_store_retention_and_since():
    store = EventStore(":memory:", max_events=10)
    for i in range(450):
        store.add({"decision": "ALLOW", "query": f"{{ a{i} }}", "ip": "1.1.1.1", "score": 1.0})
    _, total = store.list(limit=1)
    assert total < 450  # pruned in batches, always bounded
    events, newest = store.since(store.max_seq() - 3)
    assert len(events) == 3 and newest == store.max_seq()


def test_startup_warms_the_pipeline_without_recording_events(make_harness):
    h = make_harness()
    assert h.events()["total"] == 0 and h.calls == []
