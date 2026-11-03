"""Compatibility shim: the analyzer now lives in the reusable ``sentinel_core`` package."""
from sentinel_core.analysis import *  # noqa: F401,F403
from sentinel_core.analysis import (  # noqa: F401
    FEATURE_NAMES,
    INTROSPECTION_ROOTS,
    SENSITIVE_KEYWORDS,
    Analysis,
    AnalysisError,
    TooComplexToParse,
    analyze,
    count_tokens,
    vector,
)
