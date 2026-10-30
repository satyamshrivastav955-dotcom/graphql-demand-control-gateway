"""Transparent rule-based risk scoring.

Every rule adds points to a 0-100 risk score and emits an explanation carrying the
exact number of points, so the final rule score is fully attributable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

Explanation = Dict[str, Any]


def _exp(rule: str, feature: str, value, points: float, severity: str, description: str) -> Explanation:
    return {
        "rule": rule,
        "feature": feature,
        "value": value,
        "points": round(float(points), 1),
        "severity": severity,
        "description": description,
    }


def _severity(points: float) -> str:
    if points >= 40:
        return "high"
    if points >= 15:
        return "medium"
    return "low"


def _depth_points(depth: float) -> float:
    if depth <= 3:
        return 0.0
    if depth <= 5:
        return 5.0
    if depth <= 8:
        return 15.0 + (depth - 5) * 5
    if depth <= 12:
        return 30.0 + (depth - 8) * 8
    return 60.0 + (depth - 12) * 5


def evaluate(
    features: Dict[str, float],
    introspection: str = "flag",
    behavior: Optional[Mapping[str, float]] = None,
) -> Tuple[float, List[Explanation]]:
    """Return ``(rule_score, explanations)`` for one operation."""
    f = features
    behavior = behavior or {}
    out: List[Explanation] = []

    def add(rule, feature, value, points, description, severity=None):
        if points > 0:
            out.append(_exp(rule, feature, value, points, severity or _severity(points), description))

    depth = f.get("max_depth", 0)
    add("depth", "max_depth", depth, _depth_points(depth), f"Selection nesting is {int(depth)} levels deep")

    if f.get("introspection_score", 0) > 0 and introspection == "flag":
        add("introspection", "introspection_score", f["introspection_score"], 45,
            "Schema introspection (__schema/__type) is typical of reconnaissance", "medium")

    aliases = f.get("alias_count", 0)
    if aliases > 5:
        add("aliases", "alias_count", aliases, min(60, (aliases - 5) * 5),
            f"{int(aliases)} aliased fields can batch many operations into one request")

    fields = f.get("field_count", 0)
    if fields > 20:
        add("breadth", "field_count", fields, min(30, fields - 20),
            f"{int(fields)} fields selected after resolving fragments")

    dups = f.get("duplicate_field_count", 0)
    if dups > 3:
        add("duplicate_fields", "duplicate_field_count", dups, min(40, (dups - 3) * 4),
            f"{int(dups)} repeated selections of the same response key")

    cost = f.get("complexity_score", 0)
    if cost > 500:
        add("complexity", "complexity_score", cost, min(45, (cost - 500) / 100),
            f"Estimated cost {int(cost)} (fields, arguments and list-size multipliers)")

    sensitive = f.get("sensitive_field_count", 0)
    if sensitive > 0:
        add("sensitive_fields", "sensitive_field_count", sensitive, min(60, sensitive * 10),
            f"{int(sensitive)} field(s) with credential/PII-like names", "medium")

    if f.get("mutation_score", 0) > 0:
        add("mutation", "mutation_score", 1, 15, "State-changing operation", "low")
        if sensitive > 0:
            add("mutation_sensitive", "sensitive_field_count", sensitive, 20,
                "Mutation touching credential/PII-like fields", "high")

    fragments = f.get("fragment_count", 0)
    if fragments > 4:
        add("fragments", "fragment_count", fragments, min(60, fragments * 8),
            f"{int(fragments)} fragment definitions (fragment amplification risk)")

    directives = f.get("directive_count", 0)
    if directives > 8:
        add("directives", "directive_count", directives, min(30, (directives - 8) * 3),
            f"{int(directives)} directives on one operation")

    signals = sum([
        f.get("introspection_score", 0) > 0 and introspection == "flag",
        depth > 8,
        aliases > 5,
        fragments > 4,
        sensitive > 0,
        dups > 3,
    ])
    if signals >= 3:
        add("multi_vector", "signals", signals, 20, f"{signals} independent abuse signals in one operation", "high")

    if behavior.get("recent_query_count", 0) >= 20 and behavior.get("repeated_pattern_score", 0) >= 0.9:
        add("repeat_flood", "repeated_pattern_score", round(behavior["repeated_pattern_score"], 2), 20,
            "Client keeps sending the same operation at a high rate", "medium")

    score = max(0.0, min(100.0, sum(e["points"] for e in out)))
    out.sort(key=lambda e: e["points"], reverse=True)
    return round(score, 1), out
