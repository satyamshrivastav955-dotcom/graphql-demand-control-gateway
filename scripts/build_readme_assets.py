"""Generate the README graphics (animated SVG) from the project's real data.

    python scripts/build_readme_assets.py

Reads ml/reports/evaluation.json and dashboard/src/data/demoSamples.json (recorded engine output) and writes
docs/assets/*.svg. Every number drawn comes from those files, so the graphics cannot drift from the evaluation.
Animations use SMIL inside <img>-embedded SVG, which GitHub renders; with reduced motion or no animation support
the first frame is a complete, readable static image.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"

BG, SURFACE, BORDER = "#09090b", "#111113", "#27272a"
TEXT, MUTED, DIM = "#fafafa", "#a1a1aa", "#71717a"
GREEN, AMBER, RED = "#4ade80", "#fbbf24", "#f87171"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
DECISION_COLOR = {"ALLOW": GREEN, "THROTTLE": AMBER, "BLOCK": RED}


def e(s) -> str:
    return escape(str(s), quote=True)


def header(w: int, h: int, title: str, desc: str, extra_css: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-labelledby="t d"><title id="t">{e(title)}</title><desc id="d">{e(desc)}</desc>'
            f'<style>text{{font-family:{SANS}}}.m{{font-family:{MONO}}}{extra_css}</style>'
            f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{BG}" stroke="{BORDER}"/>')


def vis(t_on: float, t_off: float, total: float, fade: float = 0.25) -> str:
    """SMIL opacity window: hidden, fade in at t_on, fade out at t_off, repeating every `total` seconds."""
    pts = [0.0, t_on, t_on + fade, t_off, min(t_off + fade, total), total]
    keys, vals = [], ["0", "0", "1", "1", "0", "0"]
    last = -1.0
    for p in pts:
        p = max(p, last + 1e-6)
        keys.append(f"{min(p / total, 1.0):.5f}")
        last = p
    keys[-1] = "1"
    return (f'<animate attributeName="opacity" values="{";".join(vals)}" keyTimes="{";".join(keys)}" '
            f'dur="{total}s" repeatCount="indefinite"/>')


# --------------------------------------------------------------------------------------------------- hero
def hero(samples: dict, meta: dict) -> str:
    W, H, T = 1200, 440, 15.0
    s_ord, s_nest, s_bomb = samples["ordinary"], samples["nesting"], samples["fragments"]
    parts = [header(W, H, "GraphQL Sentinel",
                    "Animation: an ordinary query is allowed, a deeply nested query is throttled and a fragment bomb "
                    "that expands to 16,403 fields is blocked at the gate.")]
    # left copy
    parts += [
        f'<text x="52" y="130" font-size="46" font-weight="700" fill="{TEXT}" letter-spacing="-1.2">GraphQL Sentinel</text>',
        f'<text x="52" y="176" font-size="21" fill="{MUTED}">Reads the operation before it</text>',
        f'<text x="52" y="204" font-size="21" fill="{MUTED}">reaches your API.</text>',
    ]
    for i, (label, color) in enumerate((("ALLOW", GREEN), ("THROTTLE", AMBER), ("BLOCK", RED))):
        x = 52 + i * 128
        parts.append(f'<circle cx="{x + 5}" cy="262" r="5" fill="{color}"/>'
                     f'<text x="{x + 17}" y="267" font-size="14" font-weight="600" fill="{TEXT}" class="m">{label}</text>')
    parts += [
        f'<text x="52" y="318" font-size="13" fill="{DIM}" class="m">engine v{e(meta["engine_version"])} · recorded {e(meta["recorded_at"])}</text>',
        f'<text x="52" y="338" font-size="13" fill="{DIM}" class="m">open source · MIT · v1.0 pre-release</text>',
        f'<text x="52" y="388" font-size="13" fill="{MUTED}">Real engine output, not a mock-up.</text>',
    ]
    # gate
    gx = 1030
    parts.append(f'<line x1="{gx}" y1="56" x2="{gx}" y2="424" stroke="{BORDER}" stroke-width="2"/><line x1="540" y1="412" x2="{gx}" y2="412" stroke="{BORDER}" stroke-dasharray="2 6"/>'
                 f'<text x="{gx}" y="44" font-size="11" fill="{DIM}" text-anchor="middle" class="m" letter-spacing="2">GATE</text>')

    def phase(idx: int, sample: dict, kind: tuple) -> str:
        S = idx * 5.0
        color = DECISION_COLOR[sample["decision"]]
        g = ['<g opacity="0">', vis(S, S + 4.9, T, 0.3)]
        # packet
        px0, px1 = 548, 585
        size_label = f'{len(sample["query"].encode()):,} B'
        g.append(f'<g opacity="0"><animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;{S / T:.5f};{(S + 0.3) / T:.5f};'
                 f'{(S + 4.6) / T:.5f};{(S + 4.9) / T:.5f};1" dur="{T}s" repeatCount="indefinite"/>'
                 f'<rect x="0" y="-13" width="64" height="26" rx="5" fill="{SURFACE}" stroke="{MUTED}"/>'
                 f'<text x="32" y="4.5" font-size="11.5" fill="{TEXT}" text-anchor="middle" class="m">{size_label}</text>'
                 f'<animateTransform attributeName="transform" type="translate" calcMode="linear" '
                 f'values="{px0} 412;{px0} 412;{px1} 412;{px1} 412;{"1105 412" if sample["decision"] != "BLOCK" else "962 412"};'
                 f'{"1105 412" if sample["decision"] != "BLOCK" else "962 412"}" '
                 f'keyTimes="0;{S / T:.5f};{(S + 0.5) / T:.5f};{(S + 3.0) / T:.5f};{(S + 4.2) / T:.5f};1" dur="{T}s" '
                 f'repeatCount="indefinite"/></g>')
        # tree
        nodes: list[tuple[float, float, float]] = []   # x, y, appear time
        edges: list[tuple[float, float, float, float, float]] = []
        if kind[1] == "flat":
            pts = [(780, 130)] + [(700 + i * 80, 200) for i in range(3)] + [(660 + i * 60, 270) for i in range(5)][:2]
            nodes = [(x, y, S + 0.7 + i * 0.25) for i, (x, y) in enumerate(pts)]
            edges = [(780, 130, 700, 200, S + 0.8), (780, 130, 780, 200, S + 0.95), (780, 130, 860, 200, S + 1.1),
                     (700, 200, 660, 270, S + 1.25), (700, 200, 720, 270, S + 1.4)]
        elif kind[1] == "chain":
            n = 11
            pts = [(650 + i * 30, 84 + i * 22) for i in range(n)]
            nodes = [(x, y, S + 0.6 + i * 0.14) for i, (x, y) in enumerate(pts)]
            edges = [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], S + 0.7 + i * 0.14) for i in range(n - 1)]
        else:
            levels = 5
            for lv in range(levels):
                cnt = 2 ** lv
                for i in range(cnt):
                    x = 620 + (i + 0.5) * (360 / cnt)
                    y = 80 + lv * 56
                    nodes.append((x, y, S + 0.5 + lv * 0.38 + (i / cnt) * 0.12))
                    if lv > 0:
                        parent_x = 620 + ((i // 2) + 0.5) * (360 / (cnt // 2))
                        edges.append((parent_x, 80 + (lv - 1) * 56, x, y, S + 0.5 + lv * 0.38))
        for x1, y1, x2, y2, t in edges:
            g.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{DIM}" stroke-width="1" opacity="0">'
                     f'{vis(t, S + 4.5, T, 0.2)}</line>')
        r = 5 if len(nodes) < 20 else 3.6
        for x, y, t in nodes:
            g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{TEXT if kind[1] != "bomb" else MUTED}" opacity="0">{vis(t, S + 4.5, T, 0.2)}</circle>')
        # counter
        feat = sample["features"]
        if kind[1] == "bomb":
            ticks = [(0.6, "0"), (1.4, "64"), (1.9, "1,024"), (2.4, "8,192"), (2.8, f"{feat['field_count']:,}")]
            unit = "fields the server would execute"
        elif kind[1] == "chain":
            ticks = [(0.6, "1"), (1.2, "5"), (1.8, f"{feat['max_depth']} levels deep")]
            unit = "nested relation chain"
        else:
            ticks = [(0.7, "2"), (1.3, f"{feat['field_count']} fields")]
            unit = "ordinary page query"
        for i, (t0, label) in enumerate(ticks):
            t1 = ticks[i + 1][0] if i + 1 < len(ticks) else 4.5
            g.append(f'<text x="620" y="352" font-size="30" font-weight="700" fill="{TEXT}" class="m" opacity="0" '
                     f'letter-spacing="-1">{e(label)}{vis(S + t0, S + t1, T, 0.12)}</text>')
        g.append(f'<text x="620" y="376" font-size="12" fill="{DIM}" class="m" opacity="0">{e(unit)}{vis(S + 0.6, S + 4.5, T)}</text>')
        # verdict
        reasons = [(x["rule"].replace("_", " "), x["points"]) for x in sample["explanations"] if x["points"] > 0][:3]
        if sample["limit_violations"]:
            reasons = [("limit " + sample["limit_violations"][0].split(">")[0].replace("_", " "), None)] + reasons[:2]
        g.append(f'<g opacity="0">{vis(S + 3.0, S + 4.7, T, 0.25)}'
                 f'<rect x="1058" y="196" width="118" height="68" rx="8" fill="{SURFACE}" stroke="{color}" stroke-width="1.5"/>'
                 f'<text x="1117" y="226" font-size="17" font-weight="700" fill="{color}" text-anchor="middle" class="m">{sample["decision"]}</text>'
                 f'<text x="1117" y="248" font-size="12" fill="{MUTED}" text-anchor="middle" class="m">score {sample["score"]:g}</text></g>')
        for k, (rule, pts) in enumerate(reasons):
            label = rule if pts is None else f"{rule} +{pts:g}"
            g.append(f'<text x="1117" y="{286 + k * 16}" font-size="11" fill="{DIM}" text-anchor="middle" class="m" opacity="0">{e(label)}'
                     f'{vis(S + 3.2 + k * 0.15, S + 4.7, T, 0.25)}</text>')
        # gate flash
        g.append(f'<rect x="{gx - 2}" y="56" width="4" height="368" fill="{color}" opacity="0">'
                 f'<animate attributeName="opacity" values="0;0;0.9;0.25;0;0" keyTimes="0;{(S + 2.7) / T:.5f};{(S + 3.0) / T:.5f};'
                 f'{(S + 3.6) / T:.5f};{(S + 4.0) / T:.5f};1" dur="{T}s" repeatCount="indefinite"/></rect>')
        g.append("</g>")
        return "".join(g)

    parts.append(phase(0, s_ord, ("Q", "flat")))
    parts.append(phase(1, s_nest, ("Q", "chain")))
    parts.append(phase(2, s_bomb, ("434 B", "bomb")))
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------------------------------------ pipeline
def pipeline() -> str:
    W, H, T = 1200, 250, 8.0
    stages = [("Request", "POST /graphql-proxy"), ("Limits", "body · rate"), ("Parse", "AST · fragments"),
              ("Features", "depth · cost"), ("Score", "rules + model"), ("Policy", "tier → action"),
              ("Enforce", "pass · 429 · 403"), ("Upstream", "your GraphQL API")]
    parts = [header(W, H, "Request pipeline", "Eight stages from request to upstream, with audit events written for every request.")]
    parts.append(f'<circle r="6" fill="{TEXT}"><animateMotion dur="{T}s" repeatCount="indefinite" path="M36 108 L{W - 36} 108" keyPoints="0;1" keyTimes="0;1" calcMode="linear"/></circle>')
    n = len(stages)
    bw, gap = 118, (W - 2 * 36 - 118 * n) / (n - 1)
    cy = 108
    for i, (name, sub) in enumerate(stages):
        x = 36 + i * (bw + gap)
        t_on = i * (T / (n + 1))
        parts.append(f'<rect x="{x:.1f}" y="{cy - 38}" width="{bw}" height="76" rx="8" fill="{SURFACE}" stroke="{BORDER}"/>')
        parts.append(f'<rect x="{x:.1f}" y="{cy - 38}" width="{bw}" height="76" rx="8" fill="none" stroke="{TEXT}" stroke-width="1.5" opacity="0">'
                     f'{vis(t_on, t_on + T / (n + 1), T, 0.2)}</rect>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{cy - 6}" font-size="15" font-weight="650" fill="{TEXT}" text-anchor="middle">{e(name)}</text>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{cy + 16}" font-size="10.5" fill="{DIM}" text-anchor="middle" class="m">{e(sub)}</text>')
        parts.append(f'<text x="{x + 10:.1f}" y="{cy - 44}" font-size="10" fill="{DIM}" class="m">{i + 1:02d}</text>')
        if i < n - 1:
            x2 = x + bw
            parts.append(f'<line x1="{x2:.1f}" y1="{cy}" x2="{x2 + gap:.1f}" y2="{cy}" stroke="{DIM}" stroke-width="1.5"/>'
                         f'<path d="M{x2 + gap - 6:.1f} {cy - 4} L{x2 + gap:.1f} {cy} L{x2 + gap - 6:.1f} {cy + 4}" fill="none" stroke="{DIM}" stroke-width="1.5"/>')
    # audit rail
    ax = 36 + 2 * (bw + gap)
    parts.append(f'<path d="M{ax + bw / 2:.1f} {cy + 38} V190 H{W - 36 - bw / 2:.1f} V{cy + 38}" fill="none" stroke="{BORDER}" stroke-dasharray="4 5"/>')
    parts.append(f'<text x="{W / 2:.0f}" y="212" font-size="12" fill="{MUTED}" text-anchor="middle" class="m">'
                 f'every request → audit event (SQLite) · Prometheus metrics · webhook alert · live dashboard</text>')
    parts.append(f'<text x="{W / 2:.0f}" y="233" font-size="11" fill="{DIM}" text-anchor="middle" class="m">'
                 f'BLOCK never reaches the upstream · shadow mode records the real decision but forwards</text>')
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------------------------------ request log
def request_log(samples: dict) -> str:
    order = ["ordinary", "nesting", "aliases", "fragments", "recon", "stuffing"]
    names = {"ordinary": "ordinary page query", "nesting": "nesting abuse", "aliases": "alias batching",
             "fragments": "fragment bomb", "recon": "schema reconnaissance", "stuffing": "credential stuffing"}
    status = {"ALLOW": "200", "THROTTLE": "200 → 429", "BLOCK": "403"}
    W, H, T = 1200, 150 + 34 * len(order), 14.0
    parts = [header(W, H, "Recorded request log", "Six real operations and the decisions the shipped engine made for them.")]
    parts.append(f'<circle cx="28" cy="28" r="5" fill="{RED}"/><circle cx="46" cy="28" r="5" fill="{AMBER}"/><circle cx="64" cy="28" r="5" fill="{GREEN}"/>'
                 f'<text x="88" y="32" font-size="12" fill="{DIM}" class="m">gateway log · decisions recorded from the shipped engine</text>')
    parts.append(f'<line x1="0" y1="50" x2="{W}" y2="50" stroke="{BORDER}"/>')
    parts.append(f'<text x="28" y="76" font-size="11" fill="{DIM}" class="m">OPERATION</text>'
                 f'<text x="330" y="76" font-size="11" fill="{DIM}" class="m">HTTP</text>'
                 f'<text x="450" y="76" font-size="11" fill="{DIM}" class="m">DECISION</text>'
                 f'<text x="590" y="76" font-size="11" fill="{DIM}" class="m">TIER</text>'
                 f'<text x="720" y="76" font-size="11" fill="{DIM}" class="m">SCORE</text>'
                 f'<text x="810" y="76" font-size="11" fill="{DIM}" class="m">WHY (top rules)</text>')
    for i, sid in enumerate(order):
        s = samples[sid]
        y = 106 + i * 34
        t_on = 0.6 + i * 1.5
        color = DECISION_COLOR[s["decision"]]
        why = "  ".join(f'{x["rule"].replace("_", " ")}' for x in s["explanations"] if x["points"] > 0)[:44]
        if s["limit_violations"]:
            why = f'limit {s["limit_violations"][0]}'
        row = (f'<g opacity="0">{vis(t_on, T - 0.5, T, 0.3)}'
               f'<rect x="12" y="{y - 20}" width="{W - 24}" height="28" rx="6" fill="{SURFACE}"/>'
               f'<text x="28" y="{y}" font-size="13" fill="{TEXT}" class="m">{e(names[sid])}</text>'
               f'<text x="330" y="{y}" font-size="13" fill="{MUTED}" class="m">{e(status[s["decision"]])}</text>'
               f'<circle cx="457" cy="{y - 4}" r="4" fill="{color}"/>'
               f'<text x="470" y="{y}" font-size="13" font-weight="700" fill="{color}" class="m">{s["decision"]}</text>'
               f'<text x="590" y="{y}" font-size="13" fill="{MUTED}" class="m">{e(str(s["risk_tier"]).replace("_RISK", "").lower())}</text>'
               f'<text x="720" y="{y}" font-size="13" fill="{TEXT}" class="m">{s["score"]:5.1f}</text>'
               f'<text x="810" y="{y}" font-size="12" fill="{DIM}" class="m">{e(why)}</text></g>')
        parts.append(row)
    cy = 106 + len(order) * 34
    parts.append(f'<text x="28" y="{cy + 4}" font-size="13" fill="{GREEN}" class="m">$</text>'
                 f'<rect x="44" y="{cy - 9}" width="8" height="15" fill="{TEXT}"><animate attributeName="opacity" values="1;0;1" dur="1.1s" repeatCount="indefinite"/></rect>')
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------------------------------------ results
def results(ev: dict) -> str:
    methods = ev["methods"]
    W, H = 1200, 448
    parts = [header(W, H, "Detection results on the held-out benchmark",
                    "F1 and false-positive rate for hard limits only, a tuned depth/cost threshold, rules, the model alone and the shipped combination.")]
    parts.append(f'<text x="40" y="44" font-size="18" font-weight="650" fill="{TEXT}">Detection on the held-out benchmark</text>')
    parts.append(f'<text x="40" y="66" font-size="12.5" fill="{DIM}">{ev["dataset"]["n_test"]:,} synthetic operations · {ev["dataset"]["attack_ratio_test"]:.0%} abusive · seed {ev["seed"]} · '
                 f'flagged = medium risk or above, or a hard-limit violation</text>')
    base, top = 350, 110
    col_w = (W - 80) / len(methods)
    for g in (0.25, 0.5, 0.75, 1.0):
        y = base - g * (base - top)
        parts.append(f'<line x1="40" y1="{y:.1f}" x2="{W - 40}" y2="{y:.1f}" stroke="{BORDER}" stroke-dasharray="3 5"/>'
                     f'<text x="34" y="{y + 4:.1f}" font-size="10.5" fill="{DIM}" text-anchor="end" class="m">{g:.2f}</text>')
    for i, m in enumerate(methods):
        cx = 40 + (i + 0.5) * col_w
        ship = m["name"].startswith("Combined")
        for j, (key, color, label) in enumerate((("f1", TEXT if ship else MUTED, "F1"), ("fpr", RED, "FPR"))):
            val = m[key]
            hgt = max(val, 0.004) * (base - top)
            x = cx - 46 + j * 50
            parts.append(f'<rect x="{x:.1f}" y="{base - hgt:.1f}" width="42" height="{hgt:.1f}" rx="3" fill="{color}" opacity="{1 if ship or key == "fpr" else .75}">'
                         f'<animate attributeName="height" from="0" to="{hgt:.1f}" dur="0.9s" begin="{i * 0.12:.2f}s" fill="freeze"/>'
                         f'<animate attributeName="y" from="{base}" to="{base - hgt:.1f}" dur="0.9s" begin="{i * 0.12:.2f}s" fill="freeze"/></rect>')
            parts.append(f'<text x="{x + 21:.1f}" y="{base - hgt - 7:.1f}" font-size="12.5" font-weight="650" fill="{color}" text-anchor="middle" class="m">{val:.2f}</text>')
            parts.append(f'<text x="{x + 21:.1f}" y="{base + 15}" font-size="10.5" fill="{DIM}" text-anchor="middle" class="m">{label}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{base + 40}" font-size="13" font-weight="{650 if ship else 500}" fill="{TEXT if ship else MUTED}" text-anchor="middle">{e(m["name"].replace(" (production)", " (shipped)"))}</text>')
    rw = ev.get("real_world_benign")
    if rw:
        fp = rw["false_positive_rate"].get("Combined (production)")
        parts.append(f'<text x="{W - 40}" y="{H - 14}" font-size="12" fill="{MUTED}" text-anchor="end">On {rw["n"]} real benign GraphQL queries the shipped scorer flags {fp:.1%}.</text>')
    parts.append(f'<text x="40" y="{H - 14}" font-size="12" fill="{DIM}">Synthetic data, one schema: a development benchmark, not production accuracy.</text>')
    parts.append("</svg>")
    return "".join(parts)


def generalization(ev: dict) -> str:
    folds = sorted(ev["generalization"]["folds"], key=lambda f: f["ml_recall"])
    W = 1200
    row, top = 30, 118
    H = top + len(folds) * row + 84
    parts = [header(W, H, "Recall on attack categories withheld from training",
                    "For each attack category, the recall of the model alone, the rules alone and the shipped combination when that category was not in the training data.")]
    parts.append(f'<text x="40" y="44" font-size="18" font-weight="650" fill="{TEXT}">Why the model never decides alone</text>')
    parts.append(f'<text x="40" y="66" font-size="12.5" fill="{DIM}">Recall on an attack category the model was never trained on (leave-one-category-out, held-out test set)</text>')
    legend = [("Model alone", RED), ("Rules alone", MUTED), ("Shipped blend", GREEN)]
    for i, (lab, col) in enumerate(legend):
        parts.append(f'<circle cx="{44 + i * 150}" cy="92" r="5" fill="{col}"/><text x="{56 + i * 150}" y="96" font-size="12.5" fill="{MUTED}">{lab}</text>')
    x0, x1 = 290, W - 60
    for g in (0, 0.25, 0.5, 0.75, 1):
        x = x0 + g * (x1 - x0)
        parts.append(f'<line x1="{x:.1f}" y1="{top - 14}" x2="{x:.1f}" y2="{top + len(folds) * row - 10}" stroke="{BORDER}" stroke-dasharray="3 5"/>'
                     f'<text x="{x:.1f}" y="{H - 52}" font-size="10.5" fill="{DIM}" text-anchor="middle" class="m">{g:.2f}</text>')
    for i, f in enumerate(folds):
        y = top + i * row
        parts.append(f'<text x="{x0 - 16}" y="{y + 4}" font-size="13" fill="{TEXT}" text-anchor="end">{e(f["held_out_category"].replace("_", " "))}</text>')
        xs = {k: x0 + f[k] * (x1 - x0) for k in ("ml_recall", "rules_recall", "combined_recall")}
        lo, hi = min(xs.values()), max(xs.values())
        parts.append(f'<line x1="{lo:.1f}" y1="{y}" x2="{hi:.1f}" y2="{y}" stroke="{BORDER}" stroke-width="3" stroke-linecap="round"/>')
        for key, col in (("rules_recall", MUTED), ("ml_recall", RED), ("combined_recall", GREEN)):
            parts.append(f'<circle cx="{xs[key]:.1f}" cy="{y}" r="0" fill="{col}">'
                         f'<animate attributeName="r" from="0" to="6" dur="0.5s" begin="{i * 0.07:.2f}s" fill="freeze"/></circle>')
    parts.append(f'<text x="{W - 60}" y="{H - 18}" font-size="11.5" fill="{DIM}" text-anchor="end">'
                 f'In-distribution the model alone scores F1 {max(m["f1"] for m in ev["methods"] if m["name"].startswith("ML")):.2f}; withheld, it misses whole categories.</text>')
    parts.append("</svg>")
    return "".join(parts)


# -------------------------------------------------------------------------------------------- architecture
def architecture() -> str:
    W, H = 1200, 470
    parts = [header(W, H, "Architecture", "Clients reach the gateway through a TLS proxy; the gateway analyses, decides, forwards to the upstream and records every request.")]
    path = "M166 210 H336 H386 V152 H916 H926 V210 H1164"
    parts.append(f'<circle r="5" fill="{TEXT}"><animateMotion dur="6s" repeatCount="indefinite" path="{path}"/></circle>')
    parts.append(f'<circle r="5" fill="{GREEN}" opacity=".9"><animateMotion dur="6s" begin="2s" repeatCount="indefinite" path="{path}"/></circle>')

    def box(x, y, w, h, title, sub="", hi=False):
        out = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{SURFACE}" stroke="{TEXT if hi else BORDER}"/>'
               f'<text x="{x + w / 2}" y="{y + (h / 2 - (4 if sub else -5))}" font-size="14.5" font-weight="650" fill="{TEXT}" text-anchor="middle">{e(title)}</text>')
        if sub:
            out += f'<text x="{x + w / 2}" y="{y + h / 2 + 15}" font-size="11" fill="{DIM}" text-anchor="middle" class="m">{e(sub)}</text>'
        return out

    parts.append(box(36, 175, 130, 70, "Clients", "apps · scripts · browsers"))
    parts.append(box(206, 175, 130, 70, "TLS proxy", "Caddy / nginx"))
    # gateway frame
    parts.append(f'<rect x="376" y="70" width="560" height="330" rx="12" fill="none" stroke="{BORDER}" stroke-dasharray="5 6"/>'
                 f'<text x="396" y="94" font-size="12" fill="{DIM}" class="m" letter-spacing="1.5">SENTINEL GATEWAY · FastAPI</text>')
    steps = [("Validate", "size · rate"), ("Analyze", "AST · fragments"), ("Score", "rules + model"), ("Decide", "policy tiers")]
    for i, (n, s) in enumerate(steps):
        parts.append(box(396 + i * 134, 120, 118, 64, n, s, hi=(n == "Decide")))
        if i < 3:
            parts.append(f'<line x1="{514 + i * 134}" y1="152" x2="{530 + i * 134}" y2="152" stroke="{DIM}" stroke-width="1.5"/>')
    parts.append(box(396, 232, 252, 56, "Enforce", "ALLOW · THROTTLE 429 · BLOCK 403"))
    parts.append(box(668, 232, 248, 56, "Shadow mode", "record the decision, forward anyway"))
    parts.append(box(396, 320, 118, 56, "Audit store", "SQLite"))
    parts.append(box(530, 320, 118, 56, "Metrics", "Prometheus"))
    parts.append(box(664, 320, 118, 56, "Alerts", "webhook"))
    parts.append(box(798, 320, 118, 56, "Dashboard", "React · /app"))
    parts.append(box(986, 175, 178, 70, "Your GraphQL API", "the only trusted upstream", hi=True))
    # edges
    for (x1, y1, x2, y2) in ((166, 210, 206, 210), (336, 210, 376, 210), (936, 210, 986, 210)):
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{MUTED}" stroke-width="1.5"/>')
    parts.append(f'<path d="M376 210 H386 V152 H396" fill="none" stroke="{MUTED}" stroke-width="1.5"/>')
    parts.append(f'<path d="M455 184 V232" stroke="{DIM}" stroke-width="1.5" fill="none"/>')
    parts.append(f'<path d="M916 152 H926 V210 H936" fill="none" stroke="{MUTED}" stroke-width="1.5"/>')
    parts.append(f'<path d="M520 288 V320 M588 288 V304 H589 V320 M724 288 V304 H723 V320 M857 288 V320" stroke="{BORDER}" stroke-width="1.5" fill="none"/>')
    parts.append(f'<text x="{W / 2}" y="{H - 22}" font-size="12" fill="{DIM}" text-anchor="middle" class="m">'
                 f'management API behind a bearer token · optional X-API-Key on the enforcing endpoint · the upstream is reachable only through the gateway</text>')
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    ev = json.loads((ROOT / "ml" / "reports" / "evaluation.json").read_text(encoding="utf-8"))
    demo = json.loads((ROOT / "dashboard" / "src" / "data" / "demoSamples.json").read_text(encoding="utf-8"))
    samples = {s["id"]: s for s in demo["samples"]}
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "hero.svg": hero(samples, demo),
        "pipeline.svg": pipeline(),
        "request-log.svg": request_log(samples),
        "results.svg": results(ev),
        "generalization.svg": generalization(ev),
        "architecture.svg": architecture(),
    }
    for name, svg in files.items():
        (OUT / name).write_text(svg, encoding="utf-8")
        print(f"wrote docs/assets/{name} ({len(svg) / 1024:.1f} kB)")


if __name__ == "__main__":
    main()
