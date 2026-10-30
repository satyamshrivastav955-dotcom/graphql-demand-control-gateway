"""Leave-one-attack-category-out (LOCO) scoring.

In-distribution validation scores reward models that memorise the shapes the generator
produces. LOCO retrains without one attack category and scores that category, which
measures what we actually need: catching abuse patterns the model was not trained on.
This is used to choose the model and the ML blend weight (validation split only), and
again on the test split for the reported generalisation table.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

import numpy as np
import pandas as pd
from sklearn.base import clone

from backend.core.analysis import FEATURE_NAMES
from backend.core.config import Limits, PolicySettings
from backend.core.security_engine import rules
from backend.core.security_engine.limits import check_limits
from backend.core.security_engine.scorer import SecurityScorer


class FeatureFrame:
    """Analyzer features of a dataframe plus rule scores and hard-limit violations."""

    def __init__(self, df: pd.DataFrame, limits: Limits, introspection: str):
        self.df = df.reset_index(drop=True)
        feats = self.df[list(FEATURE_NAMES)].to_dict("records")
        self.violations = np.array([bool(check_limits(f, limits, introspection)) for f in feats], dtype=bool)
        self.rule_scores = np.array([rules.evaluate(f, introspection)[0] for f in feats])
        self.X = self.df[list(FEATURE_NAMES)].to_numpy(dtype=float)


@dataclass
class Fold:
    category: str
    n: int
    ml_attack: np.ndarray
    rule_attack: np.ndarray
    viol_attack: np.ndarray
    ml_benign: np.ndarray
    rule_benign: np.ndarray
    viol_benign: np.ndarray


def loco_folds(df: pd.DataFrame, template, eval_split: str, limits: Limits, introspection: str) -> List[Fold]:
    train = df[df.split == "train"]
    ev = df[df.split == eval_split]
    benign = FeatureFrame(ev[ev.label == 0], limits, introspection)
    folds = []
    for cat in sorted(df[df.label == 1].category.unique()):
        atk_rows = ev[ev.category == cat]
        if atk_rows.empty:
            continue
        fit_rows = train[~((train.label == 1) & (train.category == cat))]
        model = clone(template).fit(fit_rows[list(FEATURE_NAMES)].to_numpy(dtype=float), fit_rows["label"].to_numpy())
        atk = FeatureFrame(atk_rows, limits, introspection)
        folds.append(Fold(
            cat, len(atk.df), model.predict_proba(atk.X)[:, 1], atk.rule_scores, atk.violations,
            model.predict_proba(benign.X)[:, 1], benign.rule_scores, benign.violations))
    return folds


def flag_fn(kind: str, policy: PolicySettings, weight: float = 0.0) -> Callable:
    """Return f(ml_prob, rule_score, violation) -> bool for 'ml', 'rules' or 'combined'."""
    thr = policy.risk_tier_thresholds
    scorer = SecurityScorer(policy.model_copy(update={"ml_weight": weight}), use_model=False)

    def score(ml, rule, viol):
        if kind == "ml":
            return ml
        base = rule if kind == "rules" else np.array([scorer.combine(r, p) for r, p in zip(rule, ml, strict=False)])
        return np.where(viol, np.maximum(base, thr.high_risk + 1), base)

    def flagged(ml, rule, viol):
        s = score(ml, rule, viol)
        return s >= 0.5 if kind == "ml" else s > thr.low_risk

    return flagged


def pooled(folds: List[Fold], flagged: Callable) -> Dict[str, float]:
    """Pooled precision/recall/F1 across folds; benign rates are averaged over the fold models."""
    n_atk = sum(f.n for f in folds)
    tp = sum(float(flagged(f.ml_attack, f.rule_attack, f.viol_attack).sum()) for f in folds)
    fpr = float(np.mean([flagged(f.ml_benign, f.rule_benign, f.viol_benign).mean() for f in folds]))
    n_ben = len(folds[0].ml_benign)
    fp = fpr * n_ben
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / n_atk if n_atk else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "fpr": round(fpr, 4)}


def choose_weight(folds: List[Fold], policy: PolicySettings, grid=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)) -> Dict:
    """ML weight maximising pooled LOCO F1; the smallest weight within 0.005 of the best wins ties."""
    sweep = [{"ml_weight": w, **pooled(folds, flag_fn("combined", policy, w))} for w in grid]
    best = max(r["f1"] for r in sweep)
    chosen = min((r for r in sweep if r["f1"] >= best - 0.005), key=lambda r: r["ml_weight"])
    return {"chosen": chosen["ml_weight"], "sweep": sweep}
