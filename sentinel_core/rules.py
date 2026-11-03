"""Transparent rule-based risk scoring.

Every rule adds points to a 0-100 risk score and emits an explanation carrying the exact number of points, so the
final rule score is fully attributable. Each explanation also carries the OWASP API Security Top 10 (2023)
categories and the GraphQL attack class from :mod:`sentinel_core.catalog`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from .catalog import annotate

Explanation = Dict[str, Any]


def _exp(rule: str, feature: str, value, points: float, severity: str, description: str) -> Explanation:
    return annotate({
        "rule": rule,
        "feature": feature,
        "value": value,
        "points": round(float(points), 1),
        "severity": severity,
        "description": description,
    })


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
    cost: Optional[Mapping[str, Any]] = None,
) -> Tuple[float, List[Explanation]]:
    """Return ``(rule_score, explanations)`` for one operation.

    ``cost`` is the schema-aware cost context (``total``, ``soft``, ``hard``, ``unknown_fields``, ``by_subgraph``,
    ``subgraph_hard``, ``top``) when a schema is loaded. With it the heuristic breadth/complexity rules are replaced
    by the schema-cost rule, and the alias rule starts later because cost, not alias count, measures amplification.
    """
    f = features
    behavior = behavior or {}
    out: List[Explanation] = []

    def add(rule, feature, value, points, description, severity=None):
        if points > 0:
            out.append(_exp(rule, feature, value, points, severity or _severity(points), description))

    depth = f.get("max_depth", 0)
    add("depth", "max_depth", depth, _depth_points(depth), f"Selection nesting is {int(depth)} levels deep")

    intro = f.get("introspection_score", 0) > 0 and introspection == "flag"
    if intro:
        walk = f.get("introspection_fields", 0)
        pts = min(100.0, 45.0 + 6.0 * max(0.0, walk - 3))
        add("introspection", "introspection_fields", int(walk), pts,
            "Schema introspection (__schema/__type) is typical of reconnaissance"
            + (f"; the query walks {int(walk)} introspection fields" if walk > 3 else ""),
            "high" if pts >= 70 else "medium")

    aliases = f.get("alias_count", 0)
    alias_free = 20 if cost else 5
    alias_step = 3 if cost else 5
    if aliases > alias_free:
        add("aliases", "alias_count", aliases, min(60, (aliases - alias_free) * alias_step),
            f"{int(aliases)} aliased fields can batch many operations into one request")

    if not cost:
        fields = f.get("field_count", 0)
        if fields > 20:
            add("breadth", "field_count", fields, min(30, fields - 20),
                f"{int(fields)} fields selected after resolving fragments")

    dups = f.get("duplicate_field_count", 0)
    if dups > 3:
        add("duplicate_fields", "duplicate_field_count", dups, min(40, (dups - 3) * 4),
            f"{int(dups)} repeated selections of the same response key")

    if cost:
        total, soft, hard = cost["total"], cost["soft"], cost["hard"]
        if total > soft:
            frac = min(1.0, (total - soft) / max(1, hard - soft))
            pts = 100.0 if total > hard else 25.0 + 60.0 * frac
            top = ", ".join(f"{k} ({v:,})" for k, v in (cost.get("top") or [])[:2])
            add("schema_cost", "schema_cost", total, pts,
                f"Estimated cost {total:,} from the schema (soft limit {soft:,}, hard limit {hard:,})"
                + (f"; largest contributors: {top}" if top else ""), "high" if pts >= 60 else "medium")
        sub_hard = cost.get("subgraph_hard")
        for graph, c in (cost.get("by_subgraph") or {}).items():
            if sub_hard and c > sub_hard * 0.5:
                add("subgraph_cost", "subgraph_cost", c, min(100.0, 60.0 + 40.0 * (c - sub_hard * 0.5) / (sub_hard * 0.5)),
                    f"Subgraph '{graph}' would receive an estimated cost of {c:,} (limit {sub_hard:,})", "high")
        unknown = cost.get("unknown_fields") or []
        if unknown:
            add("unknown_fields", "unknown_field_count", len(unknown), min(100.0, 25.0 * len(unknown)),
                f"{len(unknown)} field(s) do not exist in the schema (e.g. {unknown[0]}): schema probing", "high")
    else:
        c = f.get("complexity_score", 0)
        if c > 500:
            add("complexity", "complexity_score", c, min(45, (c - 500) / 100),
                f"Estimated cost {int(c)} (fields, arguments and list-size multipliers)")

    sensitive = f.get("sensitive_field_count", 0)
    if sensitive > 0:
        add("sensitive_fields", "sensitive_field_count", sensitive, min(60, sensitive * 10),
            f"{int(sensitive)} field(s) with credential/PII-like names", "medium")

    if f.get("mutation_score", 0) > 0:
        add("mutation", "mutation_score", 1, 15, "State-changing operation", "low")
        if sensitive > 0:
            add("mutation_sensitive", "sensitive_field_count", sensitive, 20,
                "Mutation touching credential/PII-like fields", "high")

    repeat = f.get("root_field_repeat", 0)
    brute = f.get("credential_arg_count", 0) >= 1 and repeat >= 4
    if brute:
        add("auth_bruteforce", "root_field_repeat", int(repeat), min(95.0, 40.0 + 8.0 * repeat),
            f"The same credential-taking field is called {int(repeat)} times in one request", "high")

    batch = f.get("batch_size", 0)
    if batch > 5:
        add("batching", "batch_size", int(batch), min(80.0, (batch - 5) * 4.0),
            f"{int(batch)} operations in one batched request", "high" if batch > 25 else "medium")

    fragments = f.get("fragment_count", 0)
    if fragments > 4:
        add("fragments", "fragment_count", fragments, min(60, fragments * 8),
            f"{int(fragments)} fragment definitions (fragment amplification risk)")

    directives = f.get("directive_count", 0)
    if directives > 8:
        add("directives", "directive_count", directives, min(30, (directives - 8) * 3),
            f"{int(directives)} directives on one operation")

    signals = sum([
        intro,
        depth > 8,
        aliases > alias_free,
        fragments > 4,
        sensitive > 0,
        dups > 3,
        bool(cost and cost["total"] > cost["soft"]),
        brute,
    ])
    if signals >= 3:
        add("multi_vector", "signals", signals, 20, f"{signals} independent abuse signals in one operation", "high")

    if behavior.get("recent_query_count", 0) >= 20 and behavior.get("repeated_pattern_score", 0) >= 0.9:
        add("repeat_flood", "repeated_pattern_score", round(behavior["repeated_pattern_score"], 2), 20,
            "Client keeps sending the same operation at a high rate", "medium")

    score = max(0.0, min(100.0, sum(e["points"] for e in out)))
    out.sort(key=lambda e: e["points"], reverse=True)
    return round(score, 1), out
