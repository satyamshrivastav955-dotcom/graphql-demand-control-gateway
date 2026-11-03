"""Plain-dataclass configuration for the engine (no third-party dependencies).

The gateway's pydantic settings (``backend.core.config``) expose the same attribute names, so either can be passed to
the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Limits:
    max_body_bytes: int = 100_000
    max_query_length: int = 20_000
    max_depth: int = 15
    max_aliases: int = 50
    max_complexity: int = 20_000        # heuristic cost, used when no schema is loaded
    max_tokens: int = 5_000
    max_schema_cost: int = 10_000       # schema-aware cost (hard); soft limit below
    schema_cost_soft: int = 1_000
    max_subgraph_cost: int = 5_000
    max_batch_size: int = 10


@dataclass
class TierThresholds:
    safe: float = 20
    low_risk: float = 40
    medium_risk: float = 65
    high_risk: float = 85


@dataclass
class PolicyConfig:
    risk_tier_thresholds: TierThresholds = field(default_factory=TierThresholds)
    tier_actions: Dict[str, str] = field(default_factory=lambda: {
        "SAFE": "ALLOW", "LOW_RISK": "ALLOW", "MEDIUM_RISK": "ALLOW", "HIGH_RISK": "THROTTLE", "CRITICAL": "BLOCK"})
    ml_weight: Optional[float] = None
