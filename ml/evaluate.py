"""Held-out evaluation of the detection methods, using the production scoring code.

"Flagged" means the operation is at least MEDIUM_RISK (alert or enforcement) or violates a
hard limit. Enforced (decision != ALLOW) detection is reported alongside.
"""
from __future__ import annotations

import asyncio
import os
import platform
import statistics
import tempfile
import time
from itertools import product
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

from backend.core.analysis import analyze
from backend.core.config import Limits, Settings
from backend.core.security_engine import rules
from backend.core.security_engine.limits import check_limits
from backend.core.security_engine.scorer import RiskModel, SecurityScorer, tier_for

from .loco import FeatureFrame, flag_fn, loco_folds

METHODS = {
    "Hard limits only": "Gateway limits (depth, aliases, cost, size, tokens) with no scoring - what a limits-only gateway does.",
    "Depth/cost threshold": "Single depth and cost thresholds tuned on the validation split.",
    "Rule scorer": "Transparent rule scorer plus hard limits (no ML).",
    "ML classifier": "Trained classifier alone (probability >= 0.5).",
    "Combined (production)": "Rule score blended with the classifier, plus hard limits - the shipped configuration.",
}


def prf(y: np.ndarray, pred: np.ndarray) -> Dict:
    tp = int(((y == 1) & pred).sum()); fp = int(((y == 0) & pred).sum())
    tn = int(((y == 0) & ~pred).sum()); fn = int(((y == 1) & ~pred).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "fpr": round(fp / (fp + tn), 4) if fp + tn else 0.0,
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn}}


def tune_depth_cost(ff: FeatureFrame) -> Dict:
    y = ff.df["label"].to_numpy()
    depth, cost = ff.df["max_depth"].to_numpy(), ff.df["complexity_score"].to_numpy()
    best = None
    for d, c in product(range(1, 21), [None] + [25, 50, 100, 200, 400, 800, 1600, 3200, 6400]):
        pred = depth > d
        if c is not None:
            pred = pred | (cost > c)
        f1 = prf(y, pred)["f1"]
        if best is None or f1 > best[0]:
            best = (f1, d, c)
    return {"depth": best[1], "cost": best[2], "val_f1": best[0]}


def method_predictions(ff: FeatureFrame, scorer: SecurityScorer, tuned: Dict, model) -> Dict[str, Dict]:
    """flagged / enforced booleans and continuous scores for each method."""
    thr = scorer.policy.risk_tier_thresholds
    actions = scorer.policy.tier_actions
    ml = model.predict_proba(ff.X)[:, 1]
    combined = np.array([scorer.combine(r, p) for r, p in zip(ff.rule_scores, ml, strict=False)])
    # violations can only raise severity: they push the score above the high-risk threshold
    combined_v = np.where(ff.violations, np.maximum(combined, thr.high_risk + 1), combined)
    rules_v = np.where(ff.violations, np.maximum(ff.rule_scores, thr.high_risk + 1), ff.rule_scores)

    def enforced(scores):
        return np.array([(actions.get(tier_for(s, thr), "BLOCK") != "ALLOW") or v
                         for s, v in zip(scores, ff.violations, strict=False)])

    depth_pred = (ff.df["max_depth"].to_numpy() > tuned["depth"])
    if tuned["cost"] is not None:
        depth_pred = depth_pred | (ff.df["complexity_score"].to_numpy() > tuned["cost"])
    return {
        "Hard limits only": {"flag": ff.violations, "enforced": ff.violations, "score": None},
        "Depth/cost threshold": {"flag": depth_pred, "enforced": depth_pred, "score": None},
        "Rule scorer": {"flag": rules_v > thr.low_risk, "enforced": enforced(rules_v), "score": rules_v},
        "ML classifier": {"flag": ml >= 0.5, "enforced": ml >= 0.5, "score": ml},
        "Combined (production)": {"flag": combined_v > thr.low_risk, "enforced": enforced(combined_v), "score": combined_v},
    }


def _pct(values: List[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1)))]


def time_methods(df: pd.DataFrame, scorer: SecurityScorer, limits: Limits, n: int = 600, seed: int = 0) -> Dict:
    sample = df.sample(min(n, len(df)), random_state=seed)["query"].tolist()
    t_an, t_rules, t_ml = [], [], []
    for q in sample:
        t0 = time.perf_counter()
        try:
            a = analyze(q, max_tokens=limits.max_tokens)
        except Exception:  # noqa: BLE001 - parse-budget rejections are cheap and excluded
            continue
        t1 = time.perf_counter()
        rules.evaluate(a.features, scorer.introspection)
        check_limits(a.features, limits, scorer.introspection)
        t2 = time.perf_counter()
        scorer.model.predict(a.features)
        t3 = time.perf_counter()
        t_an.append((t1 - t0) * 1e6); t_rules.append((t2 - t1) * 1e6); t_ml.append((t3 - t2) * 1e6)
    pairs = lambda extra: [a + b for a, b in zip(t_an, extra, strict=False)]  # noqa: E731
    both = [a + b + c for a, b, c in zip(t_an, t_rules, t_ml, strict=False)]
    series = {
        "Hard limits only": pairs([r * 0 for r in t_rules]),
        "Depth/cost threshold": t_an,
        "Rule scorer": pairs(t_rules),
        "ML classifier": pairs(t_ml),
        "Combined (production)": both,
    }
    return {k: {"p50": round(_pct(v, 0.5), 1), "p95": round(_pct(v, 0.95), 1)} for k, v in series.items()}


def loco_table(df: pd.DataFrame, template, limits: Limits, introspection: str, policy, weight: float) -> List[Dict]:
    """Leave-one-attack-category-out on the test split: recall on a category the model never saw."""
    folds = loco_folds(df, template, "test", limits, introspection)
    ml_f, rules_f = flag_fn("ml", policy), flag_fn("rules", policy)
    comb_f = flag_fn("combined", policy, weight)
    out = []
    for f in folds:
        out.append({
            "held_out_category": f.category, "n": f.n,
            "ml_recall": round(float(ml_f(f.ml_attack, f.rule_attack, f.viol_attack).mean()), 4),
            "rules_recall": round(float(rules_f(f.ml_attack, f.rule_attack, f.viol_attack).mean()), 4),
            "combined_recall": round(float(comb_f(f.ml_attack, f.rule_attack, f.viol_attack).mean()), 4),
            "ml_fpr": round(float(ml_f(f.ml_benign, f.rule_benign, f.viol_benign).mean()), 4),
            "combined_fpr": round(float(comb_f(f.ml_benign, f.rule_benign, f.viol_benign).mean()), 4),
        })
    return out


def evaluate_confirmation(conf: pd.DataFrame, removed: int, seed: int, scorer: SecurityScorer, tuned: Dict, model,
                          limits: Limits, intro: str) -> Dict:
    """Score a second, independently generated dataset that was never used for any decision."""
    ff = FeatureFrame(conf, limits, intro)
    y = ff.df["label"].to_numpy()
    preds = method_predictions(ff, scorer, tuned, model)
    methods = []
    for name in METHODS:
        p = preds[name]
        m = prf(y, p["flag"])
        sc = p["score"]
        methods.append({"name": name, **m,
                        "roc_auc": round(float(roc_auc_score(y, sc)), 4) if sc is not None else None,
                        "pr_auc": round(float(average_precision_score(y, sc)), 4) if sc is not None else None})
    return {"seed": seed, "n": int(len(conf)), "attack_ratio": round(float(y.mean()), 4),
            "removed_overlapping_skeletons": removed, "methods": methods,
            "note": "Independently generated (different seed); operations sharing a skeleton with the training "
                    "split were removed. No threshold, weight or model choice used this set."}


def production_path_agreement(df: pd.DataFrame, settings: Settings, scorer: SecurityScorer, model, n: int = 400) -> Dict:
    """Check that the vectorised evaluation matches GraphQLGateway.evaluate on real queries."""
    from backend.api.gateway import GraphQLGateway
    from backend.core.runtime.events import EventStore

    gw = GraphQLGateway(settings, EventStore(":memory:"), scorer=scorer)
    sample = df.sample(min(n, len(df)), random_state=1)
    ff = FeatureFrame(sample, settings.limits, settings.security.introspection)
    thr = settings.security.policy.risk_tier_thresholds
    preds = method_predictions(ff, scorer, {"depth": 99, "cost": None}, model)["Combined (production)"]
    agree = 0
    for q, flag in zip(sample["query"], preds["flag"], strict=False):
        v = gw.evaluate(q)
        flagged = v.decision == "BLOCK" or (v.score is not None and v.score > thr.low_risk)
        agree += int(flagged == bool(flag))
    return {"n": int(len(sample)), "agreement": round(agree / len(sample), 4)}


async def _gateway_bench(queries: List[str], n: int = 800, concurrency: int = 16) -> Optional[Dict]:
    import httpx

    from backend.api.gateway import GraphQLGateway
    from backend.core.runtime.events import EventStore
    from backend.main import create_app

    settings = Settings.model_validate({"gateway": {"upstream_url": "http://upstream.test/graphql"},
                                        "throttle": {"rate_limit": 10_000_000, "risky_quota": 10_000_000}})

    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"ok": True}})

    tmp = tempfile.mkdtemp()
    store = EventStore(os.path.join(tmp, "bench.db"))
    gw = GraphQLGateway(settings, store, http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
    await gw.startup()
    app = create_app(settings, gw)
    app.state.gateway = gw
    qs = [queries[i % len(queries)] for i in range(n)]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sentinel") as client:
        for q in qs[:30]:
            await client.post("/graphql-proxy", json={"query": q})
        direct, proxied = [], []
        for _ in range(200):
            t = time.perf_counter(); await client.get("/api/health"); direct.append((time.perf_counter() - t) * 1e3)
        for q in qs:
            t = time.perf_counter(); await client.post("/graphql-proxy", json={"query": q})
            proxied.append((time.perf_counter() - t) * 1e3)
        t0 = time.perf_counter()
        for i in range(0, n, concurrency):
            await asyncio.gather(*[client.post("/graphql-proxy", json={"query": q}) for q in qs[i:i + concurrency]])
        rps = n / (time.perf_counter() - t0)
    store.close()
    return {"p50_ms": round(statistics.median(proxied), 2), "p95_ms": round(_pct(proxied, 0.95), 2),
            "baseline_framework_p50_ms": round(statistics.median(direct), 2),
            "requests_per_second": round(rps, 1), "n": n,
            "note": "In-process ASGI client, stub upstream (0 ms), SQLite event write per request; single process."}


def gateway_bench(queries: List[str]) -> Optional[Dict]:
    try:
        return asyncio.run(_gateway_bench(queries))
    except Exception as exc:  # noqa: BLE001
        print("gateway benchmark skipped:", exc)
        return None


def environment() -> Dict:
    import sklearn
    return {"python": platform.python_version(), "platform": platform.platform(),
            "cpu": f"{platform.processor() or platform.machine()} ({os.cpu_count()} logical cores)",
            "sklearn": sklearn.__version__}


def run_evaluation(df: pd.DataFrame, dataset_meta: Dict, model, model_meta: Dict, selection: Dict,
                   real_queries: List[str], real_meta: Dict, settings: Settings, seed: int,
                   do_bench: bool = True, confirmation: Optional[Dict] = None):
    limits, intro = settings.limits, settings.security.introspection
    scorer = SecurityScorer(settings.security.policy, intro, model=_Injected(model, model_meta))
    val = FeatureFrame(df[df.split == "val"], limits, intro)
    test = FeatureFrame(df[df.split == "test"], limits, intro)
    tuned = tune_depth_cost(val)
    preds = method_predictions(test, scorer, tuned, model)
    y = test.df["label"].to_numpy()

    methods = []
    timings = time_methods(df[df.split == "test"], scorer, limits)
    for name, desc in METHODS.items():
        p = preds[name]
        m = prf(y, p["flag"])
        enforced = prf(y, p["enforced"])
        score = p["score"]
        methods.append({
            "name": name, "description": desc, **m,
            "roc_auc": round(float(roc_auc_score(y, score)), 4) if score is not None else None,
            "pr_auc": round(float(average_precision_score(y, score)), 4) if score is not None else None,
            "enforced_recall": enforced["recall"], "enforced_fpr": enforced["fpr"],
            "latency_us_p50": timings[name]["p50"], "latency_us_p95": timings[name]["p95"],
        })

    per_category = []
    cats = test.df["category"].to_numpy()
    for cat in sorted(set(cats)):
        mask = cats == cat
        per_category.append({
            "category": cat, "n": int(mask.sum()), "is_attack": bool(y[mask][0] == 1),
            "detection_rate": {n: round(float(preds[n]["flag"][mask].mean()), 4) for n in METHODS},
        })

    real = None
    if real_queries:
        rows = []
        for q in real_queries:
            try:
                rows.append({"query": q, "label": 0, "category": "real_world", "split": "test",
                             **analyze(q, max_tokens=limits.max_tokens).features})
            except Exception:  # noqa: BLE001
                continue
        rdf = pd.DataFrame(rows)
        rff = FeatureFrame(rdf, limits, intro)
        rp = method_predictions(rff, scorer, tuned, model)
        real = {**real_meta, "n": int(len(rdf)),
                "false_positive_rate": {n: round(float(rp[n]["flag"].mean()), 4) for n in METHODS}}

    gateway = gateway_bench(df[(df.split == "test") & (df.label == 0)]["query"].tolist()) if do_bench else None
    curves = {}
    for name in ("Rule scorer", "ML classifier", "Combined (production)"):
        pr, rc, _ = precision_recall_curve(y, preds[name]["score"])
        curves[name] = (pr, rc)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": seed,
        "dataset": {"version": dataset_meta["version"], "n_train": dataset_meta["sizes"]["train"],
                    "n_val": dataset_meta["sizes"]["val"], "n_test": dataset_meta["sizes"]["test"],
                    "attack_ratio_test": dataset_meta["attack_ratio"]["test"],
                    "categories": sorted(dataset_meta["categories"])},
        "methods": methods,
        "per_category": per_category,
        "real_world_benign": real,
        "gateway_overhead": gateway,
        "generalization": {
            "description": "Leave-one-attack-category-out: the ML model is retrained without the category and "
                           "scored on that category's held-out test operations.",
            "folds": loco_table(df, model, limits, intro, settings.security.policy, scorer.weight)},
        "confirmation": confirmation_block(confirmation, scorer, tuned, model, limits, intro),
        "tuned_baseline": tuned,
        "ml_weight": {"effective": scorer.weight, "explicit_override": settings.security.policy.ml_weight,
                      "selection": "pooled leave-one-attack-category-out F1 on the validation split",
                      "validation_sweep": model_meta["ml_weight_sweep"]},
        "model": {"selected": selection["selected"], "candidates": selection["candidates"],
                  "sha256": model_meta["sha256"]},
        "production_path_check": production_path_agreement(df[df.split == "test"], settings, scorer, model),
        "limitations": [
            "Operations are synthetic, drawn from one fictional schema; labels follow generator intent, not "
            "observed attacker behaviour. Results do not predict accuracy on production traffic.",
            "Attack parameter ranges overlap benign ranges by design, so some errors are irreducible; "
            "benign heavy reports and mild attacks look alike at the feature level.",
            "Rules and generator were written by the same author, so rule recall on in-distribution categories "
            "is optimistic; the leave-one-category-out table is the better generalisation signal.",
            "The real-world benign set (NL2GQL test queries) measures false positives only; it contains no attacks.",
            "Behavioural features (rate, repetition) and the rate limiters are not part of this offline evaluation.",
            "Latency figures come from a single development machine and a stub upstream.",
            "Design-level selection bias: the generator ranges, rule thresholds and default cost limit were revised "
            "twice after reviewing aggregate results of earlier runs. The independent confirmation set guards "
            "against overfitting to specific samples, not against this; treat the numbers as a development "
            "benchmark rather than a blind validation.",
        ],
        "environment": environment(),
    }
    return report, curves


def confirmation_block(confirmation, scorer, tuned, model, limits, intro):
    if not confirmation:
        return None
    return evaluate_confirmation(confirmation["df"], confirmation["removed"], confirmation["seed"], scorer, tuned,
                                 model, limits, intro)


class _Injected(RiskModel):
    """Wrap an in-memory model so SecurityScorer can use it without a file."""

    def __init__(self, model, meta=None):  # noqa: D107 - intentionally skips file loading
        self.path, self.meta, self.error, self.model = "<memory>", meta or {}, None, model
