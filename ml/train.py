"""Select, train and persist the risk classifier (checksummed artifact + metadata)."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from datetime import UTC, datetime
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from threadpoolctl import threadpool_limits

from backend.core.analysis import FEATURE_NAMES
from backend.core.config import ROOT, Limits, PolicySettings

from .loco import choose_weight, flag_fn, loco_folds, pooled

MODEL_DIR = ROOT / "backend" / "core" / "models"
MODEL_PATH = MODEL_DIR / "risk_model.joblib"


def candidates(seed: int) -> Dict[str, object]:
    return {
        "logistic_regression": make_pipeline(
            FunctionTransformer(np.log1p), StandardScaler(),
            LogisticRegression(max_iter=2000, C=1.0, random_state=seed)),
        "random_forest": RandomForestClassifier(
            n_estimators=40, max_depth=14, min_samples_leaf=2, n_jobs=1, random_state=seed),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=100, learning_rate=0.1, max_depth=6, random_state=seed),
    }


def xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    return df[list(FEATURE_NAMES)].to_numpy(dtype=float), df["label"].to_numpy()


def _single_row_latency_us(model, X: np.ndarray, n: int = 200) -> float:
    rows = X[:n]
    with threadpool_limits(limits=1):
        model.predict_proba(rows[:1])
        start = time.perf_counter()
        for r in rows:
            model.predict_proba(r.reshape(1, -1))
    return (time.perf_counter() - start) / len(rows) * 1e6


def select_and_train(df: pd.DataFrame, seed: int, limits: Optional[Limits] = None, introspection: str = "flag",
                     policy: Optional[PolicySettings] = None) -> Tuple[object, Dict]:
    """Fit each candidate on the training split and choose by what generalises.

    Selection uses the validation split only: pooled leave-one-attack-category-out F1 for the
    classifier at p >= 0.5. Candidates within 0.01 of the best are ranked by single-row latency,
    since inference sits on the request path. The ML blend weight is then chosen the same way.
    """
    limits, policy = limits or Limits(), policy or PolicySettings()
    Xtr, ytr = xy(df[df.split == "train"])
    Xva, yva = xy(df[df.split == "val"])
    results, models = {}, {}
    for name, model in candidates(seed).items():
        model.fit(Xtr, ytr)
        p = model.predict_proba(Xva)[:, 1]
        folds = loco_folds(df, model, "val", limits, introspection)
        results[name] = {
            "val_average_precision": float(average_precision_score(yva, p)),
            "val_roc_auc": float(roc_auc_score(yva, p)),
            "val_loco": pooled(folds, flag_fn("ml", policy)),
            "predict_us_single_row": round(_single_row_latency_us(model, Xva), 1),
        }
        results[name]["_folds"] = folds
        models[name] = model
    best_f1 = max(r["val_loco"]["f1"] for r in results.values())
    eligible = [n for n, r in results.items() if r["val_loco"]["f1"] >= best_f1 - 0.01]
    best = min(eligible, key=lambda n: results[n]["predict_us_single_row"])
    weight = choose_weight(results[best].pop("_folds"), policy)
    for r in results.values():
        r.pop("_folds", None)
    return models[best], {"selected": best, "candidates": results, "weight": weight}


def build_meta(selection: Dict, dataset_meta: Dict, seed: int, sha256: str) -> Dict:
    return {
        "name": f"sentinel-risk-{selection['selected']}",
        "algorithm": selection["selected"],
        "trained_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "feature_names": list(FEATURE_NAMES),
        "sha256": sha256,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "dataset": {"version": dataset_meta["version"], "sizes": dataset_meta["sizes"],
                    "categories": sorted(dataset_meta["categories"])},
        "model_selection": selection["candidates"],
        "recommended_ml_weight": selection["weight"]["chosen"],
        "ml_weight_sweep": selection["weight"]["sweep"],
        "decision_threshold": 0.5,
        "intended_use": "Second opinion on GraphQL operation abuse risk, blended with transparent rules.",
        "limitations": "Trained on synthetic operations from a fictional schema; does not generalise to unseen "
                       "abuse categories on its own (see ml/reports/evaluation.md); not validated on production traffic.",
    }


def save_model(model, selection: Dict, dataset_meta: Dict, seed: int, path=MODEL_PATH) -> Dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(model, path)
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    meta = build_meta(selection, dataset_meta, seed, digest)
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return meta
