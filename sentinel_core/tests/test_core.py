"""Tests for the reusable engine: cost model, catalogue, persisted queries, batch evaluation, rule additions."""
import json
import re
import time
from pathlib import Path

import pytest

from sentinel_core import Allowlist, Engine, Limits, SchemaCost, analyze, build_manifest
from sentinel_core.catalog import CATALOG, OWASP_API_2023, limit_id
from sentinel_core.cost import MUTATION_BASE_COST
from sentinel_core.persisted import normalize, sha256

FIX = Path(__file__).parent
SUPERGRAPH = (FIX / "demo_supergraph.graphql").read_text(encoding="utf-8")
TWO_SUBGRAPHS = (FIX / "two_subgraphs.graphql").read_text(encoding="utf-8")


def cost(sdl, q, variables=None):
    a = analyze(q)
    return SchemaCost(sdl).estimate(a.document, a.operation, variables)


# ---- schema-aware cost ----------------------------------------------------------------------------------------
def test_list_size_comes_from_the_slicing_argument():
    assert cost(SUPERGRAPH, "{ users(first: 50) { id name } }").total == 50
    assert cost(SUPERGRAPH, "{ users(first: 50) { friends(first: 50) { id } } }").total == 50 * (1 + 50)


def test_variables_and_defaults_feed_list_sizes():
    q = "query($n: Int = 7) { users(first: $n) { id } }"
    assert cost(SUPERGRAPH, q).total == 7
    assert cost(SUPERGRAPH, q, {"n": 3}).total == 3


def test_unspecified_list_uses_assumed_size():
    assert cost(SUPERGRAPH, "{ users { id } }").total == 10


def test_mutation_base_cost():
    assert cost(SUPERGRAPH, "{ me { id } }").total == 1
    r = cost(SUPERGRAPH, 'mutation { login(email: "a", password: "b") { token } }')
    assert r.total >= MUTATION_BASE_COST


def test_cost_weight_directive_overrides_default():
    sdl = "type Query { a: A  b: Int @cost(weight: 25) } type A { x: Int }"
    assert cost(sdl, "{ a { x } b }").total == 1 + 25


def test_unknown_fields_are_reported_without_cost():
    r = cost(SUPERGRAPH, "{ usrs { id } me { id nme } }")
    assert r.unknown_fields == ["Query.usrs", "User.nme"] and r.total == 1


def test_skip_with_literal_true_is_free():
    assert cost(SUPERGRAPH, "{ users(first: 100) @skip(if: true) { id } me { id } }").total == 1


def test_fragment_bomb_is_costed_in_linear_time():
    lines = ["fragment F0 on User { id }"]
    for i in range(1, 40):
        lines.append(f"fragment F{i} on User {{ a: friends(first: 25) {{ ...F{i - 1} }} b: friends(first: 25) {{ ...F{i - 1} }} }}")
    q = "{ me { ...F39 } }\n" + "\n".join(lines)
    t = time.perf_counter()
    r = cost(SUPERGRAPH, q)
    assert r.total >= 10 ** 12 and time.perf_counter() - t < 2.0


def test_fragment_cycle_does_not_recurse_forever():
    q = "{ me { ...A } } fragment A on User { friends { ...B } } fragment B on User { friends { ...A } }"
    assert cost(SUPERGRAPH, q).total > 0


def test_cost_is_attributed_to_the_owning_subgraph():
    r = cost(TWO_SUBGRAPHS, "{ users(first: 10) { name reviews(first: 20) { body } } }")
    assert set(r.by_subgraph) == {"users", "reviews"}
    assert r.by_subgraph["reviews"] > r.by_subgraph["users"]
    assert sum(r.by_subgraph.values()) == r.total


# ---- catalogue ------------------------------------------------------------------------------------------------
def test_every_catalogue_entry_maps_to_real_owasp_categories():
    for rule in CATALOG.values():
        assert rule.owasp and set(rule.owasp) <= set(OWASP_API_2023), rule.id


def test_every_emitted_rule_and_limit_is_catalogued():
    e = Engine(schema=SchemaCost(SUPERGRAPH))
    queries = [
        "{ users(first: 1) " + "{ friends(first: 1) " * 15 + "{ id }" + " }" * 15 + " }",
        "{ __schema { types { name fields { name } } } }",
        "{ " + " ".join(f"a{i}: user(id: 1) {{ name email }}" for i in range(60)) + " }",
        "mutation { " + " ".join(f'l{i}: login(email: "a", password: "b") {{ token }}' for i in range(9)) + " }",
        "{ usrs xyz abc def }", "{ users(first: 1000) { friends(first: 1000) { friends(first: 1000) { id } } } }",
        "{ me { id } } fragment X on User { id } fragment Y on User { id } fragment Z on User { id }",
        "{ me { ...Q } } fragment Q on User { friends { ...Q } }",
    ]
    seen = set()
    for q in queries:
        v = e.evaluate(q)
        for x in v.explanations:
            assert x["rule"] in CATALOG, x
            assert x.get("owasp"), x
            seen.add(x["rule"])
        for lim in v.limit_violations:
            assert limit_id(lim) in CATALOG, lim
    assert {"depth", "introspection", "aliases", "auth_bruteforce", "schema_cost", "unknown_fields",
            "hard_limit"} <= seen


def test_owasp_doc_is_up_to_date():
    from scripts.export_owasp_mapping import render
    doc = Path(__file__).resolve().parents[2] / "docs" / "owasp-mapping.md"
    assert doc.read_text(encoding="utf-8") == render()


# ---- rules ----------------------------------------------------------------------------------------------------
def test_introspection_points_grow_with_the_size_of_the_schema_walk():
    e = Engine()
    small = e.evaluate('{ __type(name: "User") { name } }')
    full = e.evaluate("{ __schema { types { name kind fields { name args { name type { name } } } } } }")
    assert small.score < full.score and full.decision != "ALLOW"
    assert set(full.owasp) >= {"API8", "API9"}


def test_credential_guessing_is_flagged_and_maps_to_api2():
    q = "mutation { " + " ".join(f'l{i}: login(email: "a", password: "p{i}") {{ token }}' for i in range(10)) + " }"
    v = Engine().evaluate(q)
    assert v.decision == "BLOCK" or v.risk_tier in ("HIGH_RISK", "CRITICAL")
    assert "API2" in v.owasp


def test_schema_cost_blocks_shallow_but_enormous_queries_and_allows_deep_cheap_ones():
    e = Engine(schema=SchemaCost(SUPERGRAPH))
    heavy = e.evaluate("{ users(first: 200) { friends(first: 200) { friends(first: 200) { id } } } }")
    assert heavy.decision == "BLOCK" and any(v.startswith("schema_cost>") for v in heavy.limit_violations)
    cheap = e.evaluate("{ users(first: 1) { friends(first: 1) { friends(first: 1) { friends(first: 1) { friends(first: 1)"
                       " { friends(first: 1) { friends(first: 1) { id } } } } } } } }")
    assert cheap.decision == "ALLOW"
    assert e.evaluate("{ users(first: 20) { id name } }").decision == "ALLOW"


def test_explanations_carry_cost_context_and_top_contributors():
    v = Engine(schema=SchemaCost(SUPERGRAPH)).evaluate("{ users(first: 100) { friends(first: 100) { id } } }")
    e = next(x for x in v.explanations if x["rule"] == "schema_cost")
    assert "users" in e["description"] and v.cost["total"] == 100 * 101


def test_unknown_fields_raise_risk_when_a_schema_is_loaded():
    e = Engine(schema=SchemaCost(SUPERGRAPH))
    assert e.evaluate("{ usrs a b c d }").decision == "BLOCK"
    assert e.evaluate("{ me { id } }").decision == "ALLOW"


def test_per_subgraph_limit_blocks_a_hot_subgraph():
    e = Engine(limits=Limits(max_subgraph_cost=300, max_schema_cost=10 ** 6), schema=SchemaCost(TWO_SUBGRAPHS))
    v = e.evaluate("{ users(first: 10) { reviews(first: 100) { body } } }")
    assert any(x.startswith("subgraph_cost>") for x in v.limit_violations)


# ---- batching -------------------------------------------------------------------------------------------------
def test_batch_costs_add_up_and_size_is_limited():
    e = Engine(schema=SchemaCost(SUPERGRAPH))
    ok = e.evaluate_batch([{"query": "{ me { id } }"}] * 3)
    assert ok.decision == "ALLOW" and ok.features["schema_cost"] == 3
    big = e.evaluate_batch([{"query": "{ me { id } }"}] * 11)
    assert big.decision == "BLOCK" and any(v.startswith("batch_size>") for v in big.limit_violations)


def test_batch_with_invalid_operation_is_an_error():
    assert Engine().evaluate_batch([{"query": "{ me"}]).decision == "ERROR"


def test_batch_disabled():
    assert Engine(batching="block").evaluate_batch([{"query": "{ me { id } }"}]).decision == "BLOCK"


# ---- persisted operations -------------------------------------------------------------------------------------
def test_allowlist_matches_exact_and_reformatted_queries():
    q = "query Q { me { id } }"
    al = Allowlist.from_manifest(build_manifest([q]))
    assert al.contains(q) and al.contains("query   Q {\n  me {\n id } }") and not al.contains("{ me { name } }")


def test_enforced_allowlist_blocks_unregistered_operations_and_log_mode_only_notes_them():
    q = "query Q { me { id } }"
    enforce = Engine(allowlist=Allowlist.from_manifest(build_manifest([q]), "enforce"))
    assert enforce.evaluate(q).decision == "ALLOW"
    v = enforce.evaluate("{ me { name } }")
    assert v.decision == "BLOCK" and "not_in_allowlist" in v.limit_violations and "API9" in v.owasp
    log = Engine(allowlist=Allowlist.from_manifest(build_manifest([q]), "log"))
    v = log.evaluate("{ me { name } }")
    assert v.decision == "ALLOW" and any(x["rule"] == "limit:not_in_allowlist" for x in v.explanations)


def test_hash_only_requests_are_resolved_to_the_registered_body():
    q = "query Q { me { id } }"
    al = Allowlist.from_manifest({"operations": [{"id": sha256(q), "body": q}]})
    assert al.resolve(None, {"persistedQuery": {"sha256Hash": sha256(q)}}) == (q, None)
    assert al.resolve(None, {"persistedQuery": {"sha256Hash": "0" * 64}})[1] == "PersistedQueryNotFound"
    assert al.resolve(q, {"persistedQuery": {"sha256Hash": "0" * 64}})[1] is not None  # hash mismatch in enforce mode
    assert normalize("{ a   b }") == normalize("{ a b }")


def test_manifest_formats():
    q = "{ me { id } }"
    for data in ({"operations": [{"id": sha256(q), "body": q}]}, {sha256(q): q}, [q]):
        assert Allowlist.from_manifest(data).contains(q)
    with pytest.raises(ValueError):
        Allowlist.from_manifest(42)
    json.dumps(build_manifest([q]))


def test_core_has_no_framework_dependencies():
    src = "".join(p.read_text(encoding="utf-8") for p in FIX.parent.glob("*.py"))
    for banned in ("fastapi", "pydantic", "httpx", "starlette", "uvicorn"):
        assert not re.search(rf"^\s*(import|from) {banned}", src, re.M), banned
