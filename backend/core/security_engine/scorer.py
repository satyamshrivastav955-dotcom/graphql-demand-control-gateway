"""Risk scoring: transparent rules blended with an optional trained classifier.

    blended = (1 - w) * rule_score + w * 100 * ml_probability
    score   = max(blended, rule_score)   if rule_score > high_risk threshold
            = blended                    otherwise

A very high rule score is therefore never diluted by the ML model, and if the model
is missing, incompatible or fails, the score falls back to the rule score alone.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Dict, Optional

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from ..analysis import FEATURE_NAMES, vector
from ..config import PolicySettings
from . import rules

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "risk_model.joblib")


def tier_for(score: float, thresholds) -> str:
    if score <= thresholds.safe:
        return "SAFE"
    if score <= thresholds.low_risk:
        return "LOW_RISK"
    if score <= thresholds.medium_risk:
        return "MEDIUM_RISK"
    if score <= thresholds.high_risk:
        return "HIGH_RISK"
    return "CRITICAL"


class RiskModel:
    """A trained classifier plus its metadata; verified against a recorded SHA-256."""

    def __init__(self, path: str):
        self.path = path
        self.meta: Dict = {}
        self.model = None
        self.error: Optional[str] = None
        self._load()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def _load(self) -> None:
        meta_path = os.path.splitext(self.path)[0] + ".json"
        try:
            with open(meta_path, encoding="utf-8") as fh:
                self.meta = json.load(fh)
            with open(self.path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            if digest != self.meta.get("sha256"):
                raise ValueError("model checksum does not match its metadata")
            if list(self.meta.get("feature_names", [])) != list(FEATURE_NAMES):
                raise ValueError("model feature schema does not match the analyzer")
            self.model = joblib.load(self.path)
            # Single-row inference: OpenMP thread start-up costs far more than it saves. Applied once,
            # process-wide (a per-call limit costs ~50 ms).
            threadpool_limits(limits=1)
            logger.info("Loaded risk model %s", self.meta.get("name"))
        except FileNotFoundError:
            self.error = "model file not found"
            logger.warning("Risk model not found at %s; using rules only", self.path)
        except Exception as exc:  # noqa: BLE001 - any load failure must degrade to rules-only
            self.error = str(exc)
            logger.error("Risk model disabled: %s", exc)

    def predict(self, features: Dict[str, float]) -> Optional[float]:
        if not self.loaded:
            return None
        try:
            return float(self.model.predict_proba(np.asarray([vector(features)]))[0][1])
        except Exception as exc:  # noqa: BLE001
            logger.error("Model inference failed: %s", exc)
            return None


class SecurityScorer:
    def __init__(self, policy: Optional[PolicySettings] = None, introspection: str = "flag",
                 model_path: Optional[str] = None, use_model: bool = True, model: Optional[RiskModel] = None):
        self.policy = policy or PolicySettings()
        self.introspection = introspection
        if model is not None:
            self.model: Optional[RiskModel] = model
        else:
            self.model = RiskModel(model_path or DEFAULT_MODEL_PATH) if use_model else None

    @property
    def model_loaded(self) -> bool:
        return bool(self.model and self.model.loaded)

    @property
    def weight(self) -> float:
        """Effective ML blend weight: explicit setting, else the model's recommendation, else 0.4."""
        if self.policy.ml_weight is not None:
            return self.policy.ml_weight
        meta = self.model.meta if self.model else {}
        return float(meta.get("recommended_ml_weight", 0.4))

    def combine(self, rule_score: float, ml: Optional[float]) -> float:
        """Blend a rule score (0-100) with an ML probability (0-1); see the module docstring."""
        if ml is None:
            return rule_score
        w = self.weight
        score = (1 - w) * rule_score + w * 100.0 * ml
        if rule_score > self.policy.risk_tier_thresholds.high_risk:
            score = max(score, rule_score)
        return max(0.0, min(100.0, score))

    def score(self, features: Dict[str, float], behavior: Optional[Dict[str, float]] = None) -> dict:
        rule_score, explanations = rules.evaluate(features, self.introspection, behavior)
        ml = self.model.predict(features) if self.model else None
        w = self.weight
        score = round(self.combine(rule_score, ml), 1)
        if ml is not None and ml >= 0.5:
            explanations.append({
                "rule": "ml_model", "feature": "ml_probability", "value": round(ml, 3),
                "points": round(w * 100.0 * ml, 1), "severity": "medium" if ml < 0.9 else "high",
                "description": f"Trained classifier rates this operation {ml:.0%} likely abusive",
            })
        return {
            "rule_score": rule_score,
            "ml_score": None if ml is None else round(ml, 4),
            "score": score,
            "risk_tier": tier_for(score, self.policy.risk_tier_thresholds),
            "explanations": explanations,
        }
