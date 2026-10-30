import hashlib
import json

import joblib
import pytest
from pydantic import ValidationError
from sklearn.dummy import DummyClassifier

from backend.core.analysis import FEATURE_NAMES, analyze
from backend.core.config import Limits, PolicySettings, Settings, load_settings
from backend.core.features.behavioral_store import BehavioralStore
from backend.core.runtime.limiter import SlidingWindowLimiter
from backend.core.security_engine import rules
from backend.core.security_engine.limits import check_limits
from backend.core.security_engine.policy import SecurityPolicy
from backend.core.security_engine.scorer import RiskModel, SecurityScorer, tier_for


def f(q):
    return analyze(q).features


# ---- rules ------------------------------------------------------------------------------
def test_benign_query_scores_low():
    score, _ = rules.evaluate(f("query { user(id: 1) { name } }"))
    assert score <= 20


def test_explanation_points_sum_to_rule_score():
    features = f("{ " + " ".join(f"a{i}: user(id: {i}) {{ name email }}" for i in range(8)) + " }")
    score, expl = rules.evaluate(features)
    assert score == pytest.approx(min(100, sum(e["points"] for e in expl)), abs=0.2)
    assert all({"rule", "feature", "value", "points", "severity", "description"} <= e.keys() for e in expl)


def test_introspection_modes():
    q = f("{ __schema { types { name } } }")
    assert rules.evaluate(q, "flag")[0] >= 45
    assert rules.evaluate(q, "allow")[0] == 0


def test_depth_is_monotonic():
    scores = [rules.evaluate({"max_depth": d, "field_count": d})[0] for d in range(1, 20)]
    assert scores == sorted(scores)


def test_repeat_flood_rule():
    base = f("{ a }")
    s0, _ = rules.evaluate(base)
    s1, expl = rules.evaluate(base, behavior={"recent_query_count": 30, "repeated_pattern_score": 0.95})
    assert s1 > s0 and any(e["rule"] == "repeat_flood" for e in expl)


# ---- scorer / policy -----------------------------------------------------------------------
def test_tier_boundaries():
    thr = PolicySettings().risk_tier_thresholds
    assert [tier_for(s, thr) for s in (0, 20, 21, 40, 41, 65, 66, 85, 86, 100)] == [
        "SAFE", "SAFE", "LOW_RISK", "LOW_RISK", "MEDIUM_RISK", "MEDIUM_RISK", "HIGH_RISK", "HIGH_RISK",
        "CRITICAL", "CRITICAL"]


def test_scorer_without_model_uses_rules_only():
    s = SecurityScorer(use_model=False)
    out = s.score(f("{ a { b } }"))
    assert out["ml_score"] is None and out["score"] == out["rule_score"]


class _FixedModel(RiskModel):
    def __init__(self, p):
        self.path, self.meta, self.error = "<mem>", {}, None
        self.model = DummyClassifier(strategy="constant", constant=1).fit([[0] * len(FEATURE_NAMES)] * 2, [0, 1])
        self._p = p

    def predict(self, features):
        return self._p


def test_blend_and_rule_floor():
    s = SecurityScorer(PolicySettings(ml_weight=0.5), model=_FixedModel(1.0))
    assert s.combine(0, 1.0) == 50
    assert s.combine(40, 0.0) == 20
    # a critical rule score is never diluted by a confident-benign model
    assert s.combine(95, 0.0) == 95
    assert s.combine(60, None) == 60


def test_ml_explanation_added_when_model_confident():
    s = SecurityScorer(model=_FixedModel(0.95))
    assert any(e["rule"] == "ml_model" for e in s.score(f("{ a }"))["explanations"])


def test_model_checksum_and_schema_are_verified(tmp_path):
    path = tmp_path / "m.joblib"
    joblib.dump(DummyClassifier().fit([[0]], [0]), path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"sha256": "bad", "feature_names": list(FEATURE_NAMES)}))
    assert RiskModel(str(path)).loaded is False
    meta.write_text(json.dumps({"sha256": digest, "feature_names": ["other"]}))
    assert RiskModel(str(path)).loaded is False
    meta.write_text(json.dumps({"sha256": digest, "feature_names": list(FEATURE_NAMES)}))
    assert RiskModel(str(path)).loaded is True


def test_missing_model_degrades_to_rules():
    assert SecurityScorer(model_path="/nonexistent/model.joblib").model_loaded is False


def test_shipped_model_loads_and_separates_obvious_cases():
    s = SecurityScorer()
    if not s.model_loaded:
        pytest.skip("shipped model not present (run `python -m ml.run`)")
    benign = s.score(f("query { user(id: 1) { name email } }"))
    attack = s.score(f("{ " + "a { " * 14 + "x" + " }" * 14 + " }"))
    assert benign["ml_score"] < 0.5 < attack["ml_score"]


def test_policy_mapping_and_failing_closed():
    p = SecurityPolicy()
    assert [p.decide(t) for t in ("SAFE", "LOW_RISK", "MEDIUM_RISK", "HIGH_RISK", "CRITICAL")] == [
        "ALLOW", "ALLOW", "ALLOW", "THROTTLE", "BLOCK"]
    assert p.decide("SAFE", violations=["max_depth>15"]) == "BLOCK"
    assert p.decide("???") == "BLOCK"
    with pytest.raises(ValueError):
        SecurityPolicy(PolicySettings(tier_actions={"SAFE": "MAYBE"}))


def test_limit_violations():
    limits = Limits(max_depth=5, max_aliases=3, max_complexity=50, max_tokens=100, max_query_length=200)
    assert check_limits(f("{ a { b } }"), limits, "flag") == []
    deep = check_limits(f("{ a { b { c { d { e { g } } } } } }"), limits, "flag")
    assert "max_depth>5" in deep
    assert "introspection_disabled" in check_limits(f("{ __schema { types { name } } }"), limits, "block")
    assert "fragment_cycle" in check_limits({}, limits, "flag", fragment_cycle=True)


# ---- config ------------------------------------------------------------------------------
def test_env_overrides_and_validation():
    s = load_settings(env={"SENTINEL_LIMITS__MAX_DEPTH": "9", "SENTINEL_MODE": "simulation",
                           "SENTINEL_CORS_ORIGINS": "https://a.test, https://b.test"})
    assert s.limits.max_depth == 9 and s.gateway.mode == "simulation"
    assert s.cors.allow_origins == ["https://a.test", "https://b.test"]
    with pytest.raises(ValidationError):
        load_settings(env={"SENTINEL_UPSTREAM_URL": "ftp://nope"})
    with pytest.raises(ValidationError):
        load_settings(env={"SENTINEL_MODE": "fake-success"})


def test_defaults_are_production_safe():
    s = Settings()
    assert s.app.debug is False and s.gateway.mode == "proxy" and s.gateway.upstream_url is None
    assert s.cors.allow_credentials is False


# ---- limiter / behaviour --------------------------------------------------------------------
def test_sliding_window_limiter():
    now = [0.0]
    lim = SlidingWindowLimiter(2, 10, clock=lambda: now[0])
    assert lim.check("a")[0] and lim.check("a")[0]
    ok, retry = lim.check("a")
    assert not ok and 9 < retry <= 10
    assert lim.check("b")[0]  # keys are independent
    now[0] = 10.1
    assert lim.check("a")[0]


def test_limiter_memory_is_bounded():
    lim = SlidingWindowLimiter(5, 60, max_keys=100)
    for i in range(1000):
        lim.check(f"ip{i}")
    assert lim.tracked_keys() <= 100


def test_behavioral_store_features_and_bounds():
    now = [1000.0]
    store = BehavioralStore(window_seconds=60, max_history=50, max_clients=10, clock=lambda: now[0])
    for _ in range(30):
        store.record("c1", "{ a }")
        now[0] += 0.5
    feats = store.features("c1")
    assert feats["recent_query_count"] == 30 and feats["repeated_pattern_score"] > 0.9
    assert store.features("unknown")["recent_query_count"] == 0
    for i in range(100):
        store.record(f"client{i}", "{ a }")
    assert store.tracked_clients() <= 10
    now[0] += 3600
    assert store.features("client99")["recent_query_count"] == 0  # window expired
