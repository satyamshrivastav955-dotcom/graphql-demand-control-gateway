"""The decision engine: analyse -> (schema cost) -> score -> hard limits -> decide, with no web framework attached.

    from sentinel_core import Engine
    verdict = Engine().evaluate("{ me { friends { friends { friends { name } } } } }")
    verdict.decision, verdict.score, [(e["rule"], e["owasp"]) for e in verdict.explanations]
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from . import catalog
from .analysis import AnalysisError, TooComplexToParse, analyze
from .config import Limits, PolicyConfig
from .cost import SchemaCost
from .limits import check_limits
from .persisted import Allowlist
from .policy import SecurityPolicy
from .scoring import SecurityScorer, tier_for

COUNT_FEATURES = ("field_count", "alias_count", "directive_count", "complexity_score", "sensitive_field_count",
                  "introspection_score", "introspection_fields", "duplicate_field_count", "fragment_spread_count",
                  "credential_arg_count", "variable_count", "token_count", "query_length", "schema_cost",
                  "operation_count", "mutation_score")


@dataclass
class Verdict:
    decision: str
    risk_tier: Optional[str]
    score: Optional[float]
    rule_score: Optional[float]
    ml_score: Optional[float]
    features: Dict[str, float]
    explanations: List[dict]
    limit_violations: List[str]
    operation_name: Optional[str]
    operation_type: Optional[str]
    latency_ms: float
    error: Optional[str] = None
    cost: Optional[Dict[str, Any]] = None
    owasp: List[str] = field(default_factory=list)


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _owasp(explanations: Sequence[dict]) -> List[str]:
    cats = {c for e in explanations if e.get("rule") != "ml_model" for c in e.get("owasp", ())}
    return sorted(cats, key=lambda c: int(c[3:]))


class Engine:
    def __init__(self, limits: Any = None, policy: Any = None, introspection: str = "flag",
                 scorer: Optional[SecurityScorer] = None, schema: Optional[SchemaCost] = None,
                 allowlist: Optional[Allowlist] = None, subscriptions: str = "allow",
                 batching: str = "allow"):
        self.limits = limits or Limits()
        self.policy_settings = policy or PolicyConfig()
        self.introspection = introspection
        self.scorer = scorer or SecurityScorer(self.policy_settings, introspection, use_model=False)
        self.policy = SecurityPolicy(self.policy_settings)
        self.schema = schema
        self.allowlist = allowlist
        self.subscriptions = subscriptions
        self.batching = batching

    # -- single operation ----------------------------------------------------------------------------------------
    def evaluate(self, query: str, operation_name: Optional[str] = None, variables: Optional[dict] = None,
                 behavior: Optional[Dict[str, float]] = None, transport: str = "http") -> Verdict:
        """Evaluate one operation. ``transport`` is "http" or "ws"; subscriptions can be blocked on HTTP only."""
        start = time.perf_counter()
        lim = self.limits
        empty: Dict[str, Any] = dict(features={}, explanations=[], operation_name=None, operation_type=None)
        if len(query) > lim.max_query_length * 4:
            # Refuse to even tokenise absurdly large inputs.
            return self._blocked(["query_length"], start, **empty)
        try:
            analysis = analyze(query, operation_name, variables, lim.max_tokens)
        except TooComplexToParse:
            return self._blocked(["parse_budget_exceeded"], start, **empty)
        except AnalysisError as exc:
            return Verdict("ERROR", None, None, None, None, limit_violations=[], latency_ms=_ms(start),
                           error=str(exc), **empty)

        features = analysis.features
        cost_ctx: Optional[Dict[str, Any]] = None
        if self.schema is not None and analysis.document is not None and analysis.operation is not None:
            cr = self.schema.estimate(analysis.document, analysis.operation, variables)
            cost_ctx = {
                "total": cr.total, "soft": getattr(lim, "schema_cost_soft", 1000), "hard": lim.max_schema_cost,
                "subgraph_hard": getattr(lim, "max_subgraph_cost", 0), "by_subgraph": cr.by_subgraph,
                "unknown_fields": cr.unknown_fields, "top": cr.top_contributors(),
            }
            features["schema_cost"] = cr.total

        scored = self.scorer.score(features, behavior, cost_ctx)
        violations = check_limits(features, lim, self.introspection, analysis.fragment_cycle,
                                  analysis.unknown_fragments, cost_ctx)
        if analysis.operation_type == "subscription" and self.subscriptions == "block" and transport == "http":
            violations.append("subscriptions_disabled")
        if self.allowlist is not None and self.allowlist.mode != "off" and not self.allowlist.contains(query):
            if self.allowlist.mode == "enforce":
                violations.append("not_in_allowlist")
            else:
                scored["explanations"].append(catalog.annotate({
                    "rule": "limit:not_in_allowlist", "feature": "allowlist", "value": "log", "points": 0,
                    "severity": "low", "description": "Not in the persisted-operation allowlist (log mode: not blocked)"}))
        return self._finish(scored, violations, features, analysis.operation_name, analysis.operation_type, start,
                            cost_ctx)

    def _blocked(self, violations: List[str], start: float, **empty) -> Verdict:
        expl = [catalog.annotate({"rule": catalog.limit_id(v), "feature": "limits", "value": v, "points": 0,
                                  "severity": "high", "description": "Hard limit exceeded: " + v}) for v in violations]
        return Verdict("BLOCK", "CRITICAL", 100.0, 100.0, None, limit_violations=violations, latency_ms=_ms(start),
                       **{**empty, "explanations": expl}, owasp=_owasp(expl))

    def _finish(self, scored: dict, violations: List[str], features: Dict[str, float], name: Optional[str],
                op_type: Optional[str], start: float, cost_ctx: Optional[Dict[str, Any]]) -> Verdict:
        score, tier = scored["score"], scored["risk_tier"]
        expl = scored["explanations"]
        if violations:
            # Hard limits can only raise severity, never lower it.
            thr = self.policy_settings.risk_tier_thresholds
            score = max(score, thr.high_risk + 1)
            tier = tier_for(score, thr)
            hard = catalog.annotate({
                "rule": "hard_limit", "feature": "limits", "value": ", ".join(violations), "points": 0,
                "severity": "high", "description": "Hard limit exceeded: " + ", ".join(violations)})
            cats = {c for v in violations if catalog.limit_id(v) in catalog.CATALOG
                    for c in catalog.CATALOG[catalog.limit_id(v)].owasp}
            hard["owasp"] = sorted(cats | set(hard.get("owasp", ())), key=lambda c: int(c[3:]))
            expl.insert(0, hard)
        return Verdict(
            decision=self.policy.decide(tier, violations), risk_tier=tier, score=score,
            rule_score=scored["rule_score"], ml_score=scored["ml_score"], features=features, explanations=expl,
            limit_violations=violations, operation_name=name, operation_type=op_type, latency_ms=_ms(start),
            cost=cost_ctx, owasp=_owasp(expl))

    # -- batched operations --------------------------------------------------------------------------------------
    def evaluate_batch(self, operations: Sequence[dict], behavior: Optional[Dict[str, float]] = None) -> Verdict:
        """Evaluate a JSON-array request as one combined workload (counts and costs add up, depth is the maximum)."""
        start = time.perf_counter()
        n = len(operations)
        empty: Dict[str, Any] = dict(features={"batch_size": n}, explanations=[], operation_name=None,
                                     operation_type="batch")
        if self.batching == "block":
            return self._blocked(["batching_disabled"], start, **empty)
        if n > self.limits.max_batch_size:
            return self._blocked([f"batch_size>{self.limits.max_batch_size}"], start, **empty)
        parts: List[Verdict] = []
        for op in operations:
            q = op.get("query") if isinstance(op, dict) else None
            if not isinstance(q, str) or not q.strip():
                return Verdict("ERROR", None, None, None, None, limit_violations=[], latency_ms=_ms(start),
                               error="Every operation in a batch needs a non-empty 'query'", **empty)
            v = self.evaluate(q, op.get("operationName"), op.get("variables"), behavior)
            if v.decision == "ERROR":
                v.latency_ms = _ms(start)
                return v
            parts.append(v)

        merged: Dict[str, float] = {"batch_size": n}
        for k in COUNT_FEATURES:
            merged[k] = sum(p.features.get(k, 0) for p in parts)
        for k in ("max_depth", "fragment_count", "operation_count"):
            merged[k] = max((p.features.get(k, 0) for p in parts), default=0)
        merged["max_list_multiplier"] = max((p.features.get("max_list_multiplier", 1) for p in parts), default=1)
        merged["query_length"] = sum(p.features.get("query_length", 0) for p in parts)
        merged["root_field_repeat"] = self._batch_repeat(operations)

        cost_ctx = None
        if self.schema is not None:
            by_sub: Dict[str, int] = {}
            unknown: List[str] = []
            for p in parts:
                for g, c in ((p.cost or {}).get("by_subgraph") or {}).items():
                    by_sub[g] = by_sub.get(g, 0) + c
                unknown += (p.cost or {}).get("unknown_fields", [])
            cost_ctx = {"total": int(merged["schema_cost"]), "soft": getattr(self.limits, "schema_cost_soft", 1000),
                        "hard": self.limits.max_schema_cost, "subgraph_hard": getattr(self.limits, "max_subgraph_cost", 0),
                        "by_subgraph": by_sub, "unknown_fields": unknown, "top": []}
        scored = self.scorer.score(merged, behavior, cost_ctx)
        violations = check_limits(merged, self.limits, self.introspection, cost=cost_ctx)
        for p in parts:
            for v in p.limit_violations:
                if v not in violations:
                    violations.append(v)
        verdict = self._finish(scored, violations, merged, None, "batch", start, cost_ctx)
        # The batch is as bad as its worst operation.
        worst = max(parts, key=lambda p: {"ALLOW": 0, "THROTTLE": 1, "BLOCK": 2}.get(p.decision, 0))
        if {"ALLOW": 0, "THROTTLE": 1, "BLOCK": 2}[worst.decision] > {"ALLOW": 0, "THROTTLE": 1, "BLOCK": 2}[verdict.decision]:
            verdict.decision, verdict.risk_tier, verdict.score = worst.decision, worst.risk_tier, worst.score
            verdict.explanations = worst.explanations + [e for e in verdict.explanations if e not in worst.explanations]
            verdict.owasp = _owasp(verdict.explanations)
        return verdict

    @staticmethod
    def _batch_repeat(operations: Sequence[dict]) -> int:
        """Largest number of times the same root field appears across the whole batch."""
        counts: Dict[str, int] = {}
        for op in operations:
            try:
                a = analyze(op["query"], op.get("operationName"), op.get("variables"))
            except Exception:  # noqa: BLE001 - already validated by evaluate()
                continue
            for name, c in a.root_fields.items():
                counts[name] = counts.get(name, 0) + c
        return max(counts.values(), default=0)
