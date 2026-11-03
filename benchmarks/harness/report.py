"""Turn a raw harness result into the markdown tables used in BENCHMARKS.md.

    python -m benchmarks.harness.report benchmarks/results/<raw>.json [--out table.md]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from .run_benchmark import CORPUS, TARGETS, wilson

ORDER = ["baseline", "sentinel", "sentinel-schema", "sentinel-rules", "armor-default", "armor-matched", "router"]


def classify(item: dict, rec: dict) -> bool:
    """True if the system stopped (detected) this item."""
    if item["cls"] == "suggestion_probe":
        return not rec["leaked_suggestion"]
    return rec["executed_ops"] == 0


def summarize(raw: dict, corpus: dict) -> Dict[str, Any]:
    items = {i["id"]: i for i in corpus["items"]}
    out: Dict[str, Any] = {}
    for name, t in raw["targets"].items():
        det = t.get("detection")
        if not det:
            continue
        by_cls: Dict[str, List[bool]] = defaultdict(list)
        fp_group: Dict[str, List[bool]] = defaultdict(list)
        fp_split: Dict[str, List[bool]] = defaultdict(list)
        decisions: Dict[str, int] = defaultdict(int)
        reject_ms: List[float] = []
        for rec in det:
            it = items[rec["id"]]
            stopped = classify(it, rec) if it["label"] == "attack" else not rec.get("ok", rec["executed_ops"] > 0)
            if rec.get("decision"):
                decisions[f"{it['label']}:{rec['decision']}"] += 1
            if it["label"] == "attack":
                by_cls[it["cls"]].append(stopped)
                if stopped:
                    reject_ms.append(rec["ms"])
            else:
                fp_group[it["benign_group"]].append(stopped)
                fp_split[it["group"]].append(stopped)
        classes = {c: (sum(v), len(v)) for c, v in by_cls.items()}
        macro = sum(k / n for k, n in classes.values()) / len(classes)
        pooled = (sum(k for k, _ in classes.values()), sum(n for _, n in classes.values()))
        out[name] = {
            "classes": classes, "macro": macro, "pooled": pooled,
            "fp_group": {g: (sum(v), len(v)) for g, v in fp_group.items()},
            "fp_split": {g: (sum(v), len(v)) for g, v in fp_split.items()},
            "decisions": dict(decisions),
            "attack_work_reaching_upstream": sum(r["work"] for r in det if items[r["id"]]["label"] == "attack"),
        }
    return out


def fmt_rate(k: int, n: int, ci: bool = False) -> str:
    if n == 0:
        return "-"
    s = f"{100 * k / n:.0f}%"
    if ci:
        lo, hi = wilson(k, n)
        s += f" ({100 * lo:.0f}-{100 * hi:.0f})"
    return s


def render(raw: dict, corpus: dict) -> str:
    s = summarize(raw, corpus)
    names = [n for n in ORDER if n in s]
    labels = {n: TARGETS[n]["label"] for n in names}
    lines: List[str] = []
    present = {i["cls"] for i in corpus["items"] if i["label"] == "attack"}
    attack_classes = [c for c in corpus["attack_classes"] if c in present]

    lines += ["### Attack detection (share of attacks that did not reach the executor)", ""]
    lines += ["| Attack class | OWASP API 2023 | n | " + " | ".join(names) + " |",
              "|---|---|---|" + "---|" * len(names)]
    for c in attack_classes:
        n = s[names[0]]["classes"][c][1]
        lines.append(f"| {c} | {', '.join(corpus['attack_classes'][c]['owasp'])} | {n} | "
                     + " | ".join(fmt_rate(*s[x]["classes"][c]) for x in names) + " |")
    lines.append("| **macro average** | | | " + " | ".join(f"**{100 * s[x]['macro']:.0f}%**" for x in names) + " |")
    lines.append("| pooled (95% CI) | | | " + " | ".join(fmt_rate(*s[x]["pooled"], ci=True) for x in names) + " |")
    lines.append("")

    lines += ["### False positives (share of benign operations that did not get a normal answer)", ""]
    groups = sorted({g for x in names for g in s[x]["fp_group"]})
    lines += ["| Benign group | n | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for g in groups:
        n = s[names[0]]["fp_group"][g][1]
        lines.append(f"| {g} | {n} | " + " | ".join(fmt_rate(*s[x]["fp_group"][g]) for x in names) + " |")
    for split in ("typical", "heavy_legit"):
        n = s[names[0]]["fp_split"][split][1]
        lines.append(f"| **all {split}** (95% CI) | {n} | "
                     + " | ".join(f"**{fmt_rate(*s[x]['fp_split'][split], ci=True)}**" for x in names) + " |")
    lines.append("")

    lines += ["### Work reaching the upstream from attacks", "",
              "| System | Field resolutions executed (sum over all attacks, capped at 100,000 per operation) |", "|---|---|"]
    for x in names:
        lines.append(f"| {labels[x]} | {s[x]['attack_work_reaching_upstream']:,} |")
    lines.append("")

    # latency
    lat = {n: t["latency"] for n, t in raw["targets"].items() if t.get("latency")}
    if lat:
        lines += ["### Latency on benign traffic (median of repetitions; lower is better)", "",
                  "| System | c=1 p50 ms | c=1 p99 ms | c=16 req/s | c=16 p50 ms | c=16 p99 ms | errors |",
                  "|---|---|---|---|---|---|---|"]

        def med(res, key):
            vals = sorted(r[key] for r in res)
            return vals[len(vals) // 2]

        for n in [n for n in TARGETS if n in lat]:
            c1, c16 = lat[n]["c1"], lat[n]["c16"]
            err = sum(r["errors"] for r in c1 + c16)
            lines.append(f"| {TARGETS[n]['label']} | {med(c1, 'p50'):.1f} | {med(c1, 'p99'):.1f} | {med(c16, 'rps'):.0f} | "
                         f"{med(c16, 'p50'):.1f} | {med(c16, 'p99'):.1f} | {err} |")
        lines += ["", "Added latency vs the system's own unprotected baseline (c=1):", "",
                  "| System | baseline | +p50 ms | +p99 ms |", "|---|---|---|---|"]
        for n, cfg in TARGETS.items():
            if n in lat and cfg.get("baseline") and cfg["baseline"] in lat:
                b = lat[cfg["baseline"]]["c1"]
                lines.append(f"| {cfg['label']} | {cfg['baseline']} | {med(lat[n]['c1'], 'p50') - med(b, 'p50'):+.1f} | "
                             f"{med(lat[n]['c1'], 'p99') - med(b, 'p99'):+.1f} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--out")
    a = ap.parse_args()
    raw = json.loads(Path(a.raw).read_text(encoding="utf-8"))
    corpus = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
    md = render(raw, corpus)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
