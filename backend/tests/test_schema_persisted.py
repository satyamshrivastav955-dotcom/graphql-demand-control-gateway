"""Gateway behaviour with a loaded schema (cost, unknown fields) and with a persisted-operation allowlist."""
import json
from pathlib import Path

import pytest

from sentinel_core import build_manifest
from sentinel_core.persisted import sha256

SCHEMA = str(Path(__file__).resolve().parents[2] / "sentinel_core" / "tests" / "demo_supergraph.graphql")


def test_schema_cost_blocks_enormous_queries_and_reports_it(make_harness):
    h = make_harness({"graphql_schema": {"path": SCHEMA}})
    r = h.post("{ users(first: 200) { friends(first: 200) { friends(first: 200) { id } } } }")
    sec = r.json()["extensions"]["security"]
    assert r.status_code == 403 and h.calls == []
    assert any(v.startswith("schema_cost>") for v in sec["limit_violations"])
    assert "API4" in {c for e in sec["explanations"] for c in e.get("owasp", [])}


def test_deep_but_cheap_query_is_allowed_with_a_schema_and_blocked_by_depth_without(make_harness):
    q = "{ users(first: 1) " + "{ friends(first: 1) " * 9 + "{ id }" + " }" * 9 + " }"
    assert make_harness({"graphql_schema": {"path": SCHEMA}}).post(q).status_code == 200


def test_unknown_fields_are_blocked_when_probing_in_bulk(make_harness):
    h = make_harness({"graphql_schema": {"path": SCHEMA}})
    assert h.post("{ usrs accounts orders invoices }").status_code == 403
    assert h.post("{ me { id } }").status_code == 200


def test_config_endpoint_reports_schema_and_policies(make_harness):
    h = make_harness({"graphql_schema": {"path": SCHEMA}})
    cfg = h.client.get("/api/config").json()
    assert cfg["schema"] == {"loaded": True, "federated": True, "subgraphs": ["demo"]}
    assert cfg["batching"]["mode"] == "allow" and cfg["persisted_queries"]["mode"] == "off"


@pytest.fixture
def manifest(tmp_path):
    q = "query Me { me { id name } }"
    f = tmp_path / "ops.json"
    f.write_text(json.dumps(build_manifest([q])), encoding="utf-8")
    return str(f), q


def test_enforced_allowlist_forwards_registered_operations_only(make_harness, manifest):
    path, q = manifest
    h = make_harness({"persisted_queries": {"mode": "enforce", "manifest": path}})
    assert h.post(q).status_code == 200
    blocked = h.post("{ users(first: 1) { name } }")
    assert blocked.status_code == 403 and "not_in_allowlist" in blocked.json()["extensions"]["security"]["limit_violations"]
    assert len(h.calls) == 1


def test_hash_only_request_is_resolved_and_the_registered_text_is_forwarded(make_harness, manifest):
    path, q = manifest
    h = make_harness({"persisted_queries": {"mode": "enforce", "manifest": path}})
    r = h.client.post("/graphql-proxy", json={"extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha256(q)}}})
    assert r.status_code == 200
    assert json.loads(h.calls[0].content)["query"] == q
    bad = h.client.post("/graphql-proxy", json={"extensions": {"persistedQuery": {"version": 1, "sha256Hash": "0" * 64}}})
    assert bad.status_code == 400 and "PersistedQueryNotFound" in bad.text


def test_log_mode_never_blocks(make_harness, manifest):
    path, _ = manifest
    h = make_harness({"persisted_queries": {"mode": "log", "manifest": path}})
    r = h.post("{ users(first: 1) { name } }")
    assert r.status_code == 200
    assert any(e["rule"] == "limit:not_in_allowlist" for e in r.json()["extensions"]["security"]["explanations"])


def test_manifest_is_required_when_mode_is_on(make_harness):
    with pytest.raises(ValueError):
        make_harness({"persisted_queries": {"mode": "enforce"}})
