"""Management-API protection: authentication, lockout, rate limits, public surface, headers."""
import pytest
from pydantic import ValidationError

from backend.api.auth import AdminAuth
from backend.core.config import ApiSettings

from .conftest import AUTH, TOKEN, deep_query

PROTECTED = [
    ("GET", "/api/config"), ("GET", "/api/events"), ("GET", "/api/events/x"), ("GET", "/api/metrics"),
    ("GET", "/api/live"), ("POST", "/api/analyze"),
]


def anonymous(h):
    h.client.headers.pop("Authorization", None)
    return h.client


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_endpoints_reject_missing_and_wrong_tokens(make_harness, method, path):
    h = make_harness()
    c = anonymous(h)
    body = {"json": {"query": "{ a }"}} if method == "POST" else {}
    assert c.request(method, path, **body).status_code == 401
    assert c.request(method, path, headers={"Authorization": "Bearer wrong-token-000000000"}, **body).status_code == 401
    assert c.request(method, path, headers={"Authorization": f"Basic {TOKEN}"}, **body).status_code == 401
    assert c.request(method, path, headers={"Authorization": f"Bearer {TOKEN[:-1]}"}, **body).status_code == 401
    assert h.calls == []


def test_valid_token_is_accepted(make_harness):
    h = make_harness()
    c = anonymous(h)
    assert c.get("/api/config", headers=AUTH).status_code == 200
    assert c.get("/api/events", headers=AUTH).status_code == 200
    assert c.get("/api/config", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200  # scheme is case-insensitive


def test_unauthenticated_responses_leak_nothing(make_harness):
    h = make_harness()
    h.post("mutation { login(email: \"a@b.c\", password: \"hunter2\") { token } }")
    r = anonymous(h).get("/api/events")
    assert r.status_code == 401 and "hunter2" not in r.text and "login" not in r.text
    assert r.headers["www-authenticate"] == "Bearer"


def test_public_surface_is_minimal(make_harness):
    h = make_harness()
    c = anonymous(h)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/evaluation").status_code == 200
    ready = c.get("/api/ready")
    assert ready.json() == {"status": "ready"}  # no check details
    assert h.calls == []  # unauthenticated readiness never touches the upstream
    authed = c.get("/api/ready", headers=AUTH).json()
    assert authed["checks"]["upstream"] == "ok" and len(h.calls) == 1
    # the enforcing gateway itself remains public by design
    assert c.post("/graphql-proxy", json={"query": "{ a }"}).status_code == 200


def test_fails_closed_when_no_token_is_configured(make_harness):
    h = make_harness({"api": {"token": None}})
    c = anonymous(h)
    assert c.get("/api/events").status_code == 503
    assert c.get("/api/events", headers=AUTH).status_code == 503
    assert c.post("/graphql-proxy", json={"query": "{ a }"}).status_code == 200  # data path unaffected


def test_auth_can_be_disabled_explicitly_for_development(make_harness):
    h = make_harness({"api": {"auth_required": False, "token": None}})
    assert anonymous(h).get("/api/events").status_code == 200


def test_lockout_after_repeated_failures_even_with_correct_token(make_harness):
    h = make_harness({"api": {"auth_failures": 3}})
    c = anonymous(h)
    bad = {"Authorization": "Bearer nope-nope-nope-nope"}
    assert [c.get("/api/config", headers=bad).status_code for _ in range(3)] == [401, 401, 401]
    locked = c.get("/api/config", headers=AUTH)
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) >= 1
    assert c.get("/api/ready", headers=AUTH).json() == {"status": "ready"}  # locked IP is not treated as authenticated


def test_authenticated_api_is_rate_limited(make_harness):
    h = make_harness({"api": {"rate_limit_per_minute": 5}})
    codes = [h.client.get("/api/metrics").status_code for _ in range(7)]
    assert codes == [200] * 5 + [429, 429]


def test_dry_run_is_not_an_unauthenticated_oracle(make_harness):
    h = make_harness()
    assert anonymous(h).post("/api/analyze", json={"query": deep_query(14)}).status_code == 401


def test_live_stream_cap():
    auth = AdminAuth(TOKEN, True, 3, 60, 100, max_streams=2)
    assert auth.open_stream() and auth.open_stream() and not auth.open_stream()
    auth.close_stream()
    assert auth.open_stream()


def test_security_headers_and_no_store(make_harness):
    h = make_harness()
    r = h.client.get("/api/config")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer"


def test_interactive_docs_are_disabled_in_production_mode(make_harness):
    h = make_harness()
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert anonymous(h).get(path).status_code == 404


def test_token_must_be_long_enough():
    with pytest.raises(ValidationError):
        ApiSettings(token="short")
    assert ApiSettings(token=None).auth_required is True  # secure default


def test_cors_does_not_allow_credentials_or_foreign_origins_by_default(make_harness):
    h = make_harness()
    r = h.client.get("/api/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-credentials" not in r.headers


# ---- optional API keys for the enforcing endpoint ----------------------------------------------
KEY = "client-key-0123456789abcdef"
QUERY = {"query": "{ users(first: 1) { name } }"}


def keyed(make_harness, **overrides):
    return make_harness({"gateway": {"client_keys": [KEY]}, **overrides})


def test_proxy_stays_anonymous_when_no_keys_are_configured(make_harness):
    h = make_harness()
    assert anonymous(h).post("/graphql-proxy", json=QUERY).status_code == 200


def test_proxy_requires_a_key_when_configured(make_harness):
    h = keyed(make_harness)
    c = anonymous(h)
    assert c.post("/graphql-proxy", json=QUERY).status_code == 401
    assert c.post("/graphql-proxy", json=QUERY, headers={"X-API-Key": "wrong-key-000000000000"}).status_code == 401
    assert c.post("/graphql-proxy", json=QUERY, headers={"Authorization": f"Bearer {KEY}"}).status_code == 401  # wrong header
    assert h.calls == [] and h.store.list(limit=1)[1] == 0  # nothing forwarded, nothing recorded


def test_valid_key_is_accepted_and_never_forwarded_upstream(make_harness):
    h = keyed(make_harness)
    r = anonymous(h).post("/graphql-proxy", json=QUERY, headers={"X-API-Key": KEY, "Authorization": "Bearer user-jwt"})
    assert r.status_code == 200 and len(h.calls) == 1
    sent = h.calls[0].headers
    assert "x-api-key" not in sent and sent["authorization"] == "Bearer user-jwt"


def test_management_token_also_works_as_a_key(make_harness):
    h = keyed(make_harness)
    assert anonymous(h).post("/graphql-proxy", json=QUERY, headers={"X-API-Key": TOKEN}).status_code == 200


def test_key_failures_lock_out_that_ip_but_not_the_dashboard_login(make_harness):
    h = keyed(make_harness, api={"auth_failures": 3})
    c = anonymous(h)
    bad = {"X-API-Key": "wrong-key-000000000000"}
    assert [c.post("/graphql-proxy", json=QUERY, headers=bad).status_code for _ in range(3)] == [401, 401, 401]
    assert c.post("/graphql-proxy", json=QUERY, headers={"X-API-Key": KEY}).status_code == 429  # locked even with the right key
    assert c.get("/api/config", headers=AUTH).status_code == 200  # operator login unaffected


def test_key_protection_does_not_touch_public_endpoints_or_dry_run_rules(make_harness):
    h = keyed(make_harness)
    c = anonymous(h)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/events").status_code == 401
    assert c.get("/api/config", headers=AUTH).json()["client_key_required"] is True


def test_client_keys_must_be_long_enough():
    from backend.core.config import GatewaySettings, load_settings
    with pytest.raises(ValidationError):
        GatewaySettings(client_keys=["short"])
    s = load_settings(env={"SENTINEL_GATEWAY_KEYS": f"{KEY}, another-key-0123456789"})
    assert s.gateway.client_keys == [KEY, "another-key-0123456789"]
    assert load_settings(env={}).gateway.client_keys == []
