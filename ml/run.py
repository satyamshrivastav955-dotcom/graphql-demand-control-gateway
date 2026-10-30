"""End-to-end pipeline: dataset -> model -> held-out evaluation -> reports.

    python -m ml.run --seed 42            # full run, writes the model and ml/reports/*
    python -m ml.run --no-save-model      # evaluate without replacing the shipped model

Runs from the repository root. A full run takes a few minutes (dataset analysis dominates).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from backend.core.config import ROOT, load_settings  # noqa: E402

from .dataset.build import build_dataset, real_world_benign  # noqa: E402
from .evaluate import METHODS, run_evaluation  # noqa: E402
from .train import MODEL_PATH, build_meta, save_model, select_and_train  # noqa: E402

REPORTS = ROOT / "ml" / "reports"
CACHE = ROOT / "ml" / "data" / "generated"


def load_or_build(seed: int, per_category: int, rebuild: bool):
    os.makedirs(CACHE, exist_ok=True)
    data, meta_path = CACHE / f"dataset_s{seed}_n{per_category}.parquet", CACHE / f"dataset_s{seed}_n{per_category}.json"
    if data.exists() and meta_path.exists() and not rebuild:
        return pd.read_parquet(data), json.loads(meta_path.read_text())
    t = time.time()
    df, meta = build_dataset(seed, per_category)
    df.to_parquet(data)
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"dataset built in {time.time() - t:.0f}s: {meta['sizes']}")
    return df, meta


def plots(report: dict, curves: dict) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    for name, (pr, rc) in curves.items():
        ax.plot(rc, pr, label=name)
    ax.set(xlabel="Recall", ylabel="Precision", title="Precision-recall (held-out test)", ylim=(0, 1.02))
    ax.legend(loc="lower left"); fig.tight_layout(); fig.savefig(REPORTS / "pr_curves.png", dpi=140); plt.close(fig)

    cats = report["per_category"]
    names = list(METHODS)
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(cats) + 1.8))
    grid = [[c["detection_rate"][n] for n in names] for c in cats]
    im = ax.imshow(grid, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(names)), labels=names, rotation=20, ha="right", fontsize=8)
    ax.set_yticks(range(len(cats)), labels=[f"{c['category']}{'' if c['is_attack'] else ' (benign)'}" for c in cats], fontsize=8)
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7)
    ax.set_title("Share of held-out operations flagged, by category")
    fig.colorbar(im, ax=ax, fraction=0.03); fig.tight_layout(); fig.savefig(REPORTS / "per_category.png", dpi=140); plt.close(fig)


def markdown(r: dict) -> str:
    out = ["# Evaluation results", "",
           f"Generated {r['generated_at']} | seed {r['seed']} | dataset v{r['dataset']['version']} "
           f"(train {r['dataset']['n_train']}, val {r['dataset']['n_val']}, test {r['dataset']['n_test']}; "
           f"{r['dataset']['attack_ratio_test']:.0%} abusive in test)", "",
           "## Detection on the held-out test split",
           "Flagged = at least MEDIUM_RISK or a hard-limit violation. `Enf. recall/FPR` use decision != ALLOW.", "",
           "| Method | Precision | Recall | F1 | FPR | ROC-AUC | PR-AUC | Enf. recall | Enf. FPR | p50 us | p95 us |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in r["methods"]:
        f = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        out.append(f"| {m['name']} | {f(m['precision'])} | {f(m['recall'])} | {f(m['f1'])} | {f(m['fpr'])} | "
                   f"{f(m['roc_auc'])} | {f(m['pr_auc'])} | {f(m['enforced_recall'])} | {f(m['enforced_fpr'])} | "
                   f"{m['latency_us_p50']:.0f} | {m['latency_us_p95']:.0f} |")
    names = list(METHODS)
    out += ["", "## Share flagged by category (test split)", "",
            "| Category | n | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for c in r["per_category"]:
        tag = "" if c["is_attack"] else " (benign)"
        out.append(f"| {c['category']}{tag} | {c['n']} | " + " | ".join(f"{c['detection_rate'][n]:.2f}" for n in names) + " |")
    if r["real_world_benign"]:
        rw = r["real_world_benign"]
        out += ["", f"## False positives on real benign queries (n={rw['n']})", f"Source: {rw['source']}", "",
                "| Method | False-positive rate |", "|---|---|"]
        out += [f"| {n} | {v:.3f} |" for n, v in rw["false_positive_rate"].items()]
    out += ["", "## Generalisation: leave-one-attack-category-out", r["generalization"]["description"], "",
            "| Held-out category | n | ML recall | Rules recall | Combined recall | ML FPR | Combined FPR |", "|---|---|---|---|---|---|---|"]
    out += [f"| {x['held_out_category']} | {x['n']} | {x['ml_recall']:.2f} | {x['rules_recall']:.2f} | "
            f"{x['combined_recall']:.2f} | {x['ml_fpr']:.3f} | {x['combined_fpr']:.3f} |" for x in r["generalization"]["folds"]]
    sw = r["ml_weight"]
    out += ["", f"## ML blend weight (effective: {sw['effective']})", f"Chosen by {sw['selection']}.", "",
            "| ML weight | Val LOCO F1 | Precision | Recall | FPR |", "|---|---|---|---|---|"]
    out += [f"| {x['ml_weight']} | {x['f1']:.3f} | {x['precision']:.3f} | {x['recall']:.3f} | {x['fpr']:.3f} |" for x in sw["validation_sweep"]]
    if r.get("confirmation"):
        c = r["confirmation"]
        out += ["", f"## Confirmation on an independent dataset (seed {c['seed']}, n={c['n']}, {c['attack_ratio']:.0%} abusive)",
                c["note"] + f" Removed {c['removed_overlapping_skeletons']} overlapping operations.", "",
                "| Method | Precision | Recall | F1 | FPR | ROC-AUC | PR-AUC |", "|---|---|---|---|---|---|---|"]
        g = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        out += [f"| {m['name']} | {g(m['precision'])} | {g(m['recall'])} | {g(m['f1'])} | {g(m['fpr'])} | "
                f"{g(m['roc_auc'])} | {g(m['pr_auc'])} |" for m in c["methods"]]
    if r["gateway_overhead"]:
        g = r["gateway_overhead"]
        out += ["", "## Gateway overhead", f"p50 {g['p50_ms']} ms, p95 {g['p95_ms']} ms per proxied request "
                f"(framework baseline p50 {g['baseline_framework_p50_ms']} ms); {g['requests_per_second']} req/s at concurrency 16. {g['note']}"]
    out += ["", "## Model selection (validation)", "", "Selected by pooled leave-one-attack-category-out (LOCO) F1 on the validation split; latency breaks ties.", "",
            "| Candidate | Val PR-AUC (in-distribution) | Val LOCO F1 | LOCO recall | LOCO FPR | Single-row predict (us) |", "|---|---|---|---|---|---|"]
    out += [f"| {n}{' (selected)' if n == r['model']['selected'] else ''} | {v['val_average_precision']:.4f} | {v['val_loco']['f1']:.3f} | {v['val_loco']['recall']:.3f} | {v['val_loco']['fpr']:.3f} | {v['predict_us_single_row']:.0f} |"
            for n, v in r["model"]["candidates"].items()]
    pc = r["production_path_check"]
    out += ["", f"Production-path check: vectorised evaluation agrees with `GraphQLGateway.evaluate` on {pc['agreement']:.1%} of {pc['n']} sampled operations.",
            "", "## Limitations", ""] + [f"- {x}" for x in r["limitations"]]
    e = r["environment"]
    out += ["", f"Environment: Python {e['python']}, scikit-learn {e['sklearn']}, {e['platform']}, {e['cpu']}.", ""]
    return "\n".join(out)


def main() -> None:
    logging.disable(logging.INFO)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--per-category", type=int, default=1000)
    ap.add_argument("--rebuild-dataset", action="store_true")
    ap.add_argument("--no-save-model", action="store_true")
    ap.add_argument("--skip-bench", action="store_true")
    ap.add_argument("--confirm-seed", type=int, default=2718, help="seed of the independent confirmation dataset (0 = skip)")
    args = ap.parse_args()

    settings = load_settings(env={})
    df, dmeta = load_or_build(args.seed, args.per_category, args.rebuild_dataset)
    model, selection = select_and_train(df, args.seed, settings.limits, settings.security.introspection,
                                        settings.security.policy)
    print("selected model:", selection["selected"], "| ML weight:", selection["weight"]["chosen"],
          {k: v["val_loco"]["f1"] for k, v in selection["candidates"].items()})
    if args.no_save_model:
        model_meta = build_meta(selection, dmeta, args.seed, "not-saved")
    else:
        model_meta = save_model(model, selection, dmeta, args.seed)
        print("model written:", MODEL_PATH)
    confirmation = None
    if args.confirm_seed:
        cdf, _ = load_or_build(args.confirm_seed, args.per_category, args.rebuild_dataset)
        train_skeletons = set(df[df.split != "test"].skeleton)
        keep = ~cdf.skeleton.isin(train_skeletons)
        confirmation = {"df": cdf[keep], "removed": int((~keep).sum()), "seed": args.confirm_seed}
    real_q, real_meta = real_world_benign()
    report, curves = run_evaluation(df, dmeta, model, model_meta, selection, real_q, real_meta, settings, args.seed,
                                    do_bench=not args.skip_bench, confirmation=confirmation)
    os.makedirs(REPORTS, exist_ok=True)
    (REPORTS / "evaluation.json").write_text(json.dumps(report, indent=2))
    (REPORTS / "dataset.json").write_text(json.dumps(dmeta, indent=2))
    (REPORTS / "evaluation.md").write_text(markdown(report), encoding="utf-8")
    plots(report, curves)
    print((REPORTS / "evaluation.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
