import time

import pytest

from backend.core.analysis import AnalysisError, TooComplexToParse, analyze


def feats(q, **kw):
    return analyze(q, **kw).features


def test_basic_structure():
    f = feats("query { user(id: 1) { name posts { title } } }")
    assert f["max_depth"] == 3
    assert f["field_count"] == 4
    assert f["alias_count"] == 0
    assert f["mutation_score"] == 0


def test_aliases_and_duplicates():
    f = feats("{ a: user(id: 1) { name } b: user(id: 2) { name } name name name }")
    assert f["alias_count"] == 2
    assert f["duplicate_field_count"] == 2


def test_fragment_depth_is_resolved():
    # nesting hidden behind fragment spreads must count towards depth
    q = """query { user(id: 1) { ...A } }
           fragment A on User { friends { ...B } }
           fragment B on User { friends { name } }"""
    assert feats(q)["max_depth"] == 4


def test_fragment_cycle_detected_without_recursion_error():
    q = "query { a { ...A } } fragment A on T { b { ...B } } fragment B on T { c { ...A } }"
    assert analyze(q).fragment_cycle is True


def test_unknown_fragment_reported():
    assert analyze("query { a { ...Missing } }").unknown_fragments == ["Missing"]


def test_fragment_bomb_is_linear_time():
    frags = "".join(f"fragment F{i} on T {{ a ...F{i + 1} b ...F{i + 1} }} " for i in range(60)) + "fragment F60 on T { x }"
    start = time.perf_counter()
    f = feats("query { ...F0 } " + frags)
    assert time.perf_counter() - start < 1.0
    assert f["field_count"] >= 10 ** 9  # saturated, not enumerated


def test_typename_is_not_introspection():
    assert feats("{ user { __typename name } }")["introspection_score"] == 0
    assert feats("{ __schema { types { name } } }")["introspection_score"] == 1
    assert feats('{ __type(name: "User") { name } }')["introspection_score"] == 1


def test_sensitive_fields_case_insensitive():
    assert feats("{ u { creditCard apiKey Password } }")["sensitive_field_count"] == 3


def test_mutation_flag():
    assert feats('mutation { login(password: "x") { token } }')["mutation_score"] == 1


def test_operation_selection():
    q = "query A { a } query B { b { c } }"
    assert analyze(q, "B").features["max_depth"] == 2
    assert analyze(q, "A").operation_name == "A"
    with pytest.raises(AnalysisError):
        analyze(q)  # ambiguous
    with pytest.raises(AnalysisError):
        analyze(q, "C")  # unknown


def test_syntax_errors_and_empty_documents():
    with pytest.raises(AnalysisError):
        analyze("query {")
    with pytest.raises(AnalysisError):
        analyze("fragment F on T { a }")


def test_token_budget():
    with pytest.raises(TooComplexToParse):
        analyze("{ " + "a " * 100 + "}", max_tokens=50)


def test_pathological_nesting_does_not_crash_the_parser():
    with pytest.raises(TooComplexToParse):
        analyze("{ a " * 3000 + "}" * 3000, max_tokens=100_000)


def test_list_multipliers_use_literals_and_variables():
    literal = feats("{ users(first: 100) { posts(first: 100) { title } } }")
    assert literal["max_list_multiplier"] == 10_000
    assert literal["complexity_score"] > 10_000
    via_var = analyze("query($n: Int) { users(first: $n) { name } }", variables={"n": 500}).features
    assert via_var["max_list_multiplier"] == 500
    assert feats("{ users(first: 100) { name } }")["complexity_score"] < feats("{ users(first: 100) { posts(first: 100) { title } } }")["complexity_score"]
