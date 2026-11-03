"""sentinel_core: explainable, OWASP-mapped GraphQL operation analysis and policy decisions.

Depends only on ``graphql-core``. The optional trained classifier needs the ``ml`` extra.
"""
from .analysis import (
    FEATURE_NAMES,
    Analysis,
    AnalysisError,
    TooComplexToParse,
    analyze,
    vector,
)
from .catalog import CATALOG, OWASP_API_2023, RuleInfo
from .config import Limits, PolicyConfig, TierThresholds
from .cost import CostResult, SchemaCost
from .engine import Engine, Verdict
from .persisted import Allowlist, build_manifest
from .policy import SecurityPolicy
from .scoring import RiskModel, SecurityScorer, tier_for

__version__ = "1.1.0"
__all__ = [
    "FEATURE_NAMES", "Analysis", "AnalysisError", "TooComplexToParse", "analyze", "vector", "CATALOG",
    "OWASP_API_2023", "RuleInfo", "Limits", "PolicyConfig", "TierThresholds", "CostResult", "SchemaCost", "Engine",
    "Verdict", "Allowlist", "build_manifest", "SecurityPolicy", "RiskModel", "SecurityScorer", "tier_for",
]
