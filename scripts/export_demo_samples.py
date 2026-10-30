"""Record real engine output for the landing page's interactive demo.

    python scripts/export_demo_samples.py

Runs a handful of representative operations through the shipped analyzer, rules, model and policy (the same
`GraphQLGateway.evaluate` the gateway uses) and writes `dashboard/src/data/demoSamples.json`, so the landing page
shows what the engine actually decides rather than hand-written numbers. Re-run after retraining or changing rules.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.api.gateway import GraphQLGateway
from backend.core.config import ROOT, load_settings
from backend.core.runtime.events import EventStore

FEATURES = ["max_depth", "field_count", "alias_count", "fragment_count", "introspection_score",
            "sensitive_field_count", "complexity_score", "token_count"]


def deep(n: int) -> str:
    inner = "name"
    for _ in range(n - 1):
        inner = f"friends {{ {inner} }}"
    return "query Deep {\n  user(id: \"1\") { " + inner + " }\n}"


def bomb(levels: int = 8) -> str:
    frags = [f"fragment L{i} on User {{ id ...L{i + 1} ...L{i + 1} ...L{i + 1} }}" for i in range(levels)]
    frags.append(f"fragment L{levels} on User {{ id name }}")
    return "query Bomb {\n  users(first: 5) { ...L0 }\n}\n" + "\n".join(frags)


SAMPLES = [
    ("ordinary", "Ordinary page query", "A typical profile view.",
     'query Profile {\n  user(id: "42") {\n    name\n    avatarUrl\n    posts(first: 5) {\n      title\n      createdAt\n    }\n  }\n}'),
    ("nesting", "Nesting abuse", "Ten levels of a cyclic relation: cheap to send, expensive to resolve.", deep(10)),
    ("aliases", "Alias batching", "Sixty aliased lookups in one request, past the hard limit.",
     "query Batch {\n" + "\n".join(f'  u{i}: user(id: "{i}") {{ email }}' for i in range(60)) + "\n}"),
    ("fragments", "Fragment bomb", "Eight fragments each spreading the next three times: the expanded query is astronomically large, the document is tiny.", bomb()),
    ("recon", "Schema reconnaissance", "A full introspection query, typical of the first step of an attack.",
     "query IntrospectionQuery {\n  __schema {\n    types {\n      name\n      fields { name type { name kind } }\n    }\n  }\n}"),
    ("stuffing", "Credential stuffing", "Forty login attempts aliased into one mutation.",
     "mutation Stuff {\n" + "\n".join(f'  t{i}: login(email: "victim{i}@example.com", password: "Winter{i}!") {{ token }}' for i in range(40)) + "\n}"),
]


def main() -> None:
    settings = load_settings(env={})
    gw = GraphQLGateway(settings, EventStore(":memory:"))
    meta = gw.scorer.model.meta if gw.scorer.model and gw.scorer.model.loaded else {}
    out = []
    for sid, title, blurb, query in SAMPLES:
        v = gw.evaluate(query)
        out.append({
            "id": sid, "title": title, "blurb": blurb, "query": query,
            "decision": v.decision, "risk_tier": v.risk_tier, "score": v.score, "rule_score": v.rule_score,
            "ml_score": v.ml_score, "limit_violations": v.limit_violations,
            "explanations": [{k: e[k] for k in ("rule", "feature", "value", "points", "severity", "description")}
                             for e in v.explanations],
            "features": {k: v.features.get(k) for k in FEATURES},
        })
    payload = {
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "engine_version": settings.app.version,
        "model": meta.get("name"),
        "model_trained_at": meta.get("trained_at"),
        "ml_weight": gw.scorer.weight,
        "note": "Recorded by running each query through the shipped engine (scripts/export_demo_samples.py).",
        "samples": out,
    }
    target = Path(ROOT) / "dashboard" / "src" / "data" / "demoSamples.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for s in out:
        print(f"{s['id']:10s} {s['decision']:9s} {str(s['risk_tier']):12s} score={s['score']}  rule={s['rule_score']}  ml={s['ml_score']}  limits={s['limit_violations']}")


if __name__ == "__main__":
    main()
