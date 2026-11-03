"""Gateway-side scorer: the reusable scorer from ``sentinel_core`` with the bundled model path as its default."""
from __future__ import annotations

import os
from typing import Optional

import sentinel_core.scoring as _core
from sentinel_core.scoring import RiskModel, tier_for  # noqa: F401

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "risk_model.joblib")


class SecurityScorer(_core.SecurityScorer):
    def __init__(self, policy=None, introspection: str = "flag", model_path: Optional[str] = None,
                 use_model: bool = True, model: Optional[RiskModel] = None):
        super().__init__(policy, introspection, model_path or DEFAULT_MODEL_PATH, use_model, model)
