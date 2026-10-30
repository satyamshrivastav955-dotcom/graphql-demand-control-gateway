"""Hard limits: deterministic checks that always result in BLOCK when violated."""
from __future__ import annotations

from typing import Dict, List

from ..config import Limits


def check_limits(features: Dict[str, float], limits: Limits, introspection: str,
                 fragment_cycle: bool = False, unknown_fragments: List[str] | None = None) -> List[str]:
    violations: List[str] = []
    if features.get("query_length", 0) > limits.max_query_length:
        violations.append(f"query_length>{limits.max_query_length}")
    if features.get("max_depth", 0) > limits.max_depth:
        violations.append(f"max_depth>{limits.max_depth}")
    if features.get("alias_count", 0) > limits.max_aliases:
        violations.append(f"alias_count>{limits.max_aliases}")
    if features.get("complexity_score", 0) > limits.max_complexity:
        violations.append(f"complexity>{limits.max_complexity}")
    if features.get("token_count", 0) > limits.max_tokens:
        violations.append(f"token_count>{limits.max_tokens}")
    if introspection == "block" and features.get("introspection_score", 0) > 0:
        violations.append("introspection_disabled")
    if fragment_cycle:
        violations.append("fragment_cycle")
    if unknown_fragments:
        violations.append("unknown_fragment")
    return violations
