"""Build the labelled, de-duplicated, split dataset used for training and evaluation."""
from __future__ import annotations

import hashlib
import random
import re
from collections import Counter
from typing import Dict, List, Tuple

import pandas as pd

from backend.core.analysis import FEATURE_NAMES, AnalysisError, analyze

from .generator import CATEGORIES, generate

DATASET_VERSION = "1.0"
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_NUMBER = re.compile(r"(?<![\w$])\d+(?:\.\d+)?")
_WS = re.compile(r"\s+")


def skeleton(query: str) -> str:
    """Query with literals and formatting removed; identical skeletons are duplicates."""
    q = _STRING.sub('""', query)
    q = _NUMBER.sub("0", q)
    return _WS.sub(" ", q).strip()


def build_dataset(seed: int = 42, per_category: int = 1500, split=(0.6, 0.2, 0.2)) -> Tuple[pd.DataFrame, Dict]:
    rows: List[dict] = []
    stats: Dict[str, Dict[str, int]] = {}
    seen = set()
    for cat in CATEGORIES:
        generated = generate(cat, per_category, seed)
        kept = dup = bad = 0
        for q in generated:
            sk = hashlib.sha1(skeleton(q).encode()).hexdigest()
            if sk in seen:
                dup += 1
                continue
            try:
                feats = analyze(q, max_tokens=200_000).features
            except AnalysisError:
                bad += 1
                continue
            seen.add(sk)
            kept += 1
            rows.append({"query": q, "label": cat.label, "category": cat.name, "skeleton": sk, **feats})
        stats[cat.name] = {"generated": per_category, "duplicates_removed": dup, "invalid_removed": bad, "kept": kept}

    df = pd.DataFrame(rows)
    rng = random.Random(seed)
    df["split"] = ""
    for _cat, idx in df.groupby("category").groups.items():
        idx = list(idx)
        rng.shuffle(idx)
        n_train, n_val = int(len(idx) * split[0]), int(len(idx) * split[1])
        df.loc[idx[:n_train], "split"] = "train"
        df.loc[idx[n_train:n_train + n_val], "split"] = "val"
        df.loc[idx[n_train + n_val:], "split"] = "test"

    meta = {
        "version": DATASET_VERSION,
        "seed": seed,
        "per_category_requested": per_category,
        "categories": {c.name: {"label": c.label, **stats[c.name]} for c in CATEGORIES},
        "sizes": {s: int((df.split == s).sum()) for s in ("train", "val", "test")},
        "attack_ratio": {s: round(float(df[df.split == s].label.mean()), 4) for s in ("train", "val", "test")},
        "feature_names": list(FEATURE_NAMES),
        "split_policy": "stratified by category after skeleton-level de-duplication (no skeleton appears twice)",
    }
    return df, meta


def real_world_benign() -> Tuple[List[str], Dict]:
    """Real GraphQL queries from the NL2GQL test set (benign by construction), de-duplicated."""
    from backend.core.config import ROOT

    path = ROOT / "ml" / "data" / "processed" / "NL2GQL_Testset_V20.1.parquet"
    if not path.exists():
        return [], {}
    col = pd.read_parquet(path)["cleaned_query"].dropna()
    queries, seen = [], set()
    for q in col:
        sk = skeleton(q)
        if sk in seen:
            continue
        seen.add(sk)
        queries.append(q)
    return queries, {"source": "NL2GQL_Testset_V20.1 (cleaned_query, de-duplicated by skeleton)", "n": len(queries)}


if __name__ == "__main__":
    df, meta = build_dataset()
    print(meta["sizes"], meta["attack_ratio"])
    print(Counter(df.category).most_common())
