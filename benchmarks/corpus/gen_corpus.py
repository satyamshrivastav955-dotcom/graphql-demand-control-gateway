"""Deterministic attack + benign corpus for the head-to-head benchmark.

    python -m benchmarks.corpus.gen_corpus            # writes benchmarks/corpus/corpus.json

Labelling rules (fixed before any system was run; see benchmarks/README.md):

* Work classes (deep_nesting, fragment_bomb, list_amplification) are ATTACKS only if the exact ground-truth work
  (field resolutions, ``ground_truth.py``) is >= ATTACK_WORK_MIN. Benign operations must have work <= BENIGN_WORK_MAX.
  Operations in between are never generated, so labels never depend on a threshold that a tool under test could be
  tuned to.
* Count classes (alias_flood, credential_stuffing, batching, directive_overload, token_bloat, sensitive_enumeration)
  are attacks above a count that no benign group reaches; the gap between the largest benign and smallest attack
  value is deliberate and recorded as ``param``.
* Reconnaissance classes (introspection_abuse, suggestion_probe) assume a production endpoint where introspection is
  not an intended feature.
* The corpus is written by the author of one of the tools under test. Parameter ranges were set before running any
  system, but the bias this implies is a stated limitation.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from benchmarks.corpus.ground_truth import work

ATTACK_WORK_MIN = 50_000
BENIGN_WORK_MAX = 5_000

# "dev" is the corpus Sentinel was developed against; "heldout" uses another seed, other parameter values and extra
# shapes, was generated after the dev work was finished and is only used for the final published run.
PROFILES: Dict[str, Dict[str, Any]] = {
    "dev": dict(
        seed=20261102,
        depth=[10, 11, 12, 14, 16, 20, 25, 30, 40], first=[3, 5, 10, 25], frag_levels=(4, 12), frag_first=[3, 5, 25],
        amp_first=[100, 200, 500, 1000], aliases=[150, 200, 300, 500, 800, 1000], stuffing=[30, 50, 100, 200],
        batch=[20, 50, 100, 200], directives=[150, 250, 400, 800], tokens=[2000, 2500, 3000, 4000],
        enum=[25, 40, 80, 150], stay_under=False, extra_benign=False),
    "heldout": dict(
        seed=20270314,
        depth=[9, 13, 15, 17, 22, 35], first=[2, 4, 8, 20, 50], frag_levels=(5, 11), frag_first=[2, 4, 10],
        amp_first=[150, 300, 700, 1000], aliases=[120, 250, 400, 700], stuffing=[25, 60, 150],
        batch=[15, 40, 120], directives=[120, 300, 600], tokens=[2200, 3500, 4500],
        enum=[30, 60, 120], stay_under=True, extra_benign=True),
}

OWASP = {
    "API1": "Broken Object Level Authorization",
    "API2": "Broken Authentication",
    "API3": "Broken Object Property Level Authorization",
    "API4": "Unrestricted Resource Consumption",
    "API6": "Unrestricted Access to Sensitive Business Flows",
    "API8": "Security Misconfiguration",
    "API9": "Improper Inventory Management",
}

INTROSPECTION_FULL = """query IntrospectionQuery { __schema { queryType { name } mutationType { name } types { ...FullType }
 directives { name description locations args { ...InputValue } } } }
fragment FullType on __Type { kind name description fields(includeDeprecated: true) { name description args { ...InputValue }
 type { ...TypeRef } isDeprecated deprecationReason } inputFields { ...InputValue } interfaces { ...TypeRef }
 enumValues(includeDeprecated: true) { name description isDeprecated deprecationReason } possibleTypes { ...TypeRef } }
fragment InputValue on __InputValue { name description type { ...TypeRef } defaultValue }
fragment TypeRef on __Type { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name
 ofType { kind name ofType { kind name ofType { kind name } } } } } } } }"""

# attack class -> (OWASP API Security 2023 categories, attack class label, short description)
ATTACKS: Dict[str, Dict[str, Any]] = {
    "deep_nesting": dict(owasp=["API4"], desc="Cyclic relations nested 10-40 levels deep"),
    "fragment_bomb": dict(owasp=["API4"], desc="Aliased fragments that double per level (exponential expansion)"),
    "list_amplification": dict(owasp=["API4"], desc="Shallow queries that multiply large page sizes"),
    "alias_flood": dict(owasp=["API4"], desc="150-1000 aliases of the same lookup in one request"),
    "credential_stuffing": dict(owasp=["API2", "API4"], desc="Aliased login mutations (password guessing in one request)"),
    "batching": dict(owasp=["API2", "API4"], desc="JSON-array requests with 20-200 operations"),
    "directive_overload": dict(owasp=["API4"], desc="150-800 @include/@skip directives"),
    "token_bloat": dict(owasp=["API4"], desc="Oversized documents of 2000-4500 tokens"),
    "introspection_abuse": dict(owasp=["API8", "API9"], desc="Full or deeply recursive schema introspection"),
    "suggestion_probe": dict(owasp=["API8", "API9"], desc="Misspelled fields to harvest 'Did you mean' suggestions"),
    "sensitive_enumeration": dict(owasp=["API1", "API3"], desc="Aliased lookups of apiToken/email across many ids"),
    "stay_under": dict(owasp=["API4"], desc="Work-heavy queries sized just under common default limits (held-out only)"),
}


def chain(field: str, depth: int, first: int, leaf: str = "id", root: str = "users(first: 2)") -> str:
    inner = leaf
    for _ in range(depth - 2):
        inner = f"{field}(first: {first}) {{ {inner} }}"
    return "{ " + root + " { " + inner + " } }"


def cyc(depth: int, first: int) -> str:
    """posts -> author -> posts -> author ... mixed relations."""
    parts: List[str] = []
    for i in range(depth - 1):
        parts.append("author {" if i % 2 == 0 else f"posts(first: {first}) {{")
    return "{ posts(first: 2) { " + " ".join(parts) + " id " + "}" * len(parts) + " } }"


def frag_bomb(levels: int, first: int) -> str:
    lines = ["fragment F0 on User { id name }"]
    for i in range(1, levels + 1):
        lines.append(f"fragment F{i} on User {{ a: friends(first: {first}) {{ ...F{i - 1} }} b: friends(first: {first}) {{ ...F{i - 1} }} }}")
    return "{ me { ...F" + str(levels) + " } }\n" + "\n".join(lines)


def _item(cls: str, label: str, body: Any, group: str, param: Any, query: Optional[str] = None, **extra) -> Dict[str, Any]:
    q = query if query is not None else (body.get("query") if isinstance(body, dict) else None)
    out = {"cls": cls, "label": label, "group": group, "param": param, "body": body,
           "bytes": len(json.dumps(body)), **extra}
    if label == "attack":
        out["owasp"] = ATTACKS[cls]["owasp"]
    out["work"] = work(q) if q and cls not in ("introspection_abuse", "suggestion_probe") else None
    return out


def gen_attacks(rng: random.Random, P: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    n = 40

    # deep_nesting: friends chains and mixed cycles
    made = 0
    while made < n:
        depth = rng.choice(P["depth"])
        first = rng.choice(P["first"])
        q = chain("friends", depth, first) if rng.random() < 0.6 else cyc(depth, first)
        if work(q) >= ATTACK_WORK_MIN:
            items.append(_item("deep_nesting", "attack", {"query": q}, "work", depth))
            made += 1

    # fragment_bomb
    made = 0
    while made < n:
        lv = rng.randint(*P["frag_levels"])
        q = frag_bomb(lv, rng.choice(P["frag_first"]))
        if work(q) >= ATTACK_WORK_MIN:
            items.append(_item("fragment_bomb", "attack", {"query": q}, "work", lv))
            made += 1

    # list_amplification: shallow (<= 4 levels), large pages
    made = 0
    while made < n:
        k = rng.choice([2, 3, 4])
        first = rng.choice(P["amp_first"])
        inner = "id"
        for _ in range(k - 1):
            inner = f"friends(first: {first}) {{ {inner} }}"
        root = rng.choice(["users", "posts"])
        if root == "posts":
            inner = f"comments(first: {first}) {{ replies(first: {first}) {{ id }} }}"
            q = "{ posts(first: %d) { %s } }" % (first, inner)
        else:
            q = "{ users(first: %d) { %s } }" % (first, inner)
        if work(q) >= ATTACK_WORK_MIN:
            items.append(_item("list_amplification", "attack", {"query": q}, "work", first))
            made += 1

    # alias_flood
    for _ in range(n):
        k = rng.choice(P["aliases"])
        q = "{ " + " ".join(f'a{i}: user(id: "{rng.randint(1, 200)}") {{ id }}' for i in range(k)) + " }"
        items.append(_item("alias_flood", "attack", {"query": q}, "count", k))

    # credential_stuffing
    for _ in range(n):
        k = rng.choice(P["stuffing"])
        q = "mutation { " + " ".join(
            f'l{i}: login(email: "user{rng.randint(1, 200)}@example.test", password: "pw{i}") {{ token }}' for i in range(k)) + " }"
        items.append(_item("credential_stuffing", "attack", {"query": q}, "count", k))

    # batching
    for _ in range(n):
        k = rng.choice(P["batch"])
        if rng.random() < 0.5:
            ops = [{"query": f'{{ user(id: "{rng.randint(1, 200)}") {{ id name }} }}'} for _ in range(k)]
        else:
            ops = [{"query": f'mutation {{ login(email: "u{i}@example.test", password: "pw{i}") {{ token }} }}'} for i in range(k)]
        items.append(_item("batching", "attack", ops, "count", k, query=None))

    # directive_overload
    for _ in range(n):
        k = rng.choice(P["directives"])
        q = "{ " + " ".join(f"d{i}: me {{ id @include(if: true) }}" for i in range(k)) + " }"
        items.append(_item("directive_overload", "attack", {"query": q}, "count", k))

    # token_bloat: duplicates of a scalar (cheap to execute, costly to parse/validate)
    for _ in range(n):
        k = rng.choice(P["tokens"])
        q = '{ user(id: "1") { ' + " ".join(["id"] * k) + " } }"
        items.append(_item("token_bloat", "attack", {"query": q}, "count", k))

    # introspection_abuse
    deep = "{ __schema { types { fields { type { fields { type { fields { type { name } } } } } } } } }"
    for i in range(n):
        if i % 4 == 0:
            q = INTROSPECTION_FULL
        elif i % 4 == 1:
            q = deep
        elif i % 4 == 2:
            q = '{ __schema { types { name kind fields { name args { name type { name } } } } } }'
        else:
            q = "{ " + " ".join(f'__type(name: "{t}") {{ name fields {{ name }} }}'.replace("__type", f"t{j}: __type")
                                for j, t in enumerate(["User", "Post", "Comment", "Mutation", "AuthPayload", "Query"])) + " }"
        items.append(_item("introspection_abuse", "attack", {"query": q}, "recon", i % 4))

    # suggestion_probe
    stems = ["usr", "usrs", "passwrd", "emial", "tokn", "frends", "pst", "comment", "admn", "secrt", "apiTokn", "rol"]
    for _ in range(30):
        k = rng.randint(4, 12)
        names = rng.sample(stems, min(k, len(stems)))
        q = "{ " + " ".join(f"{s}" for s in names) + " }"
        items.append(_item("suggestion_probe", "attack", {"query": q}, "recon", len(names)))

    # sensitive_enumeration
    for _ in range(n):
        k = rng.choice(P["enum"])
        q = "{ " + " ".join(f'u{i}: user(id: "{i + 1}") {{ email apiToken }}' for i in range(k)) + " }"
        items.append(_item("sensitive_enumeration", "attack", {"query": q}, "count", k))

    if P["stay_under"]:
        # Attacks sized to sit just under the documented defaults of the tools under test: depth <= 10, aliases <= 40,
        # fewer than 1000 tokens, but still >= ATTACK_WORK_MIN of real work.
        made = 0
        while made < n:
            if rng.random() < 0.5:
                d = rng.randint(6, 10)
                q = chain("friends", d, rng.choice([8, 10, 20, 25]))
            else:
                k = rng.randint(10, 14)
                inner = "friends(first: 200) { friends(first: 25) { id } }"
                q = "{ " + " ".join(f"a{i}: users(first: 100) {{ {inner} }}" for i in range(k)) + " }"
            if work(q) >= ATTACK_WORK_MIN:
                items.append(_item("stay_under", "attack", {"query": q}, "work", work(q)))
                made += 1
    return items


def gen_benign(rng: random.Random, P: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    def add(group: str, cls: str, q: str, variables: Optional[dict] = None, param: Any = None, heavy: bool = False):
        body: Dict[str, Any] = {"query": q}
        if variables:
            body["variables"] = variables
        w = work(q, variables)
        assert w <= BENIGN_WORK_MAX, (cls, w, q[:120])
        it = _item(cls, "benign", body, "heavy_legit" if heavy else "typical", param)
        it["work"] = w
        it["benign_group"] = group
        items.append(it)

    n = 40
    for _ in range(n):  # lookups
        i = rng.randint(1, 200)
        add("lookup", "lookup", rng.choice([
            f'{{ user(id: "{i}") {{ id name username }} }}',
            f'{{ post(id: "{rng.randint(1, 600)}") {{ id title }} }}',
            f'{{ product(id: "{rng.randint(1, 30)}") {{ id name price stock }} }}',
            "{ me { id name role } }", "{ __typename }"]))
    for _ in range(n):  # list pages
        f = rng.choice([5, 10, 20])
        add("list_page", "list_page", rng.choice([
            f"{{ users(first: {f}) {{ id name username }} }}",
            f"{{ posts(first: {f}) {{ id title author {{ name }} }} }}",
            f"{{ products(first: {f}) {{ id name price }} }}"]))
    for _ in range(n):  # nested views
        f = rng.choice([2, 3, 5])
        add("nested_view", "nested_view", rng.choice([
            f"{{ posts(first: {f}) {{ title author {{ name }} comments(first: {f}) {{ text author {{ name }} }} }} }}",
            f'{{ user(id: "{rng.randint(1, 200)}") {{ name friends(first: {f}) {{ name posts(first: 2) {{ title }} }} }} }}',
            f"{{ users(first: {f}) {{ name posts(first: {f}) {{ title comments(first: 2) {{ text }} }} }} }}"]))
    for _ in range(n):  # dashboards: several roots, some aliases
        k = rng.randint(3, 10)
        parts = [f"p{i}: posts(first: {rng.choice([2, 3])}) {{ id title }}" for i in range(k // 2)]
        parts += ["me { id name }", f"products(first: {rng.choice([3, 5])}) {{ id price }}"]
        add("dashboard", "dashboard", "query Dashboard { " + " ".join(parts) + " }", param=k)
    for _ in range(n):  # fragments reuse
        f = rng.choice([2, 3, 5])
        add("fragments", "fragments", "query Feed { posts(first: %d) { ...P } me { ...U } }"
            " fragment U on User { id name username } fragment P on Post { id title author { ...U } }" % f)
    for _ in range(n):  # mutations
        if rng.random() < 0.5:
            add("mutation", "mutation", 'mutation { login(email: "user%d@example.test", password: "correct-horse") { token user { id name } } }' % rng.randint(1, 200))
        else:
            add("mutation", "mutation", 'mutation { createPost(title: "Hello %d", body: "text") { id title } }' % rng.randint(1, 999))
    for _ in range(n):  # variables
        f = rng.choice([3, 5, 10])
        add("variables", "variables", "query Page($n: Int, $id: ID!) { users(first: $n) { id name } user(id: $id) { name } }",
            {"n": f, "id": str(rng.randint(1, 200))})
    for _ in range(n):  # small legitimate batches (apollo-link-batch-http style)
        k = rng.randint(2, 5)
        ops = [{"query": f'{{ user(id: "{rng.randint(1, 200)}") {{ id name }} }}'} for _ in range(k)]
        it = _item("batch_small", "benign", ops, "typical", k)
        it["work"] = 3 * k
        it["benign_group"] = "batch_small"
        items.append(it)

    # heavy-but-legitimate: unusual shapes that naive limits flag
    for _ in range(n):  # deep but cheap: depth 7-9 with first: 1
        d = rng.randint(7, 9)
        add("deep_cheap", "deep_cheap", chain("friends", d, 1, root="users(first: 1)"), param=d, heavy=True)
    for _ in range(n):  # wide report: 40-70 distinct scalar selections across aliases of cheap roots
        k = rng.randint(40, 60)
        sel = " ".join(f"p{i}: product(id: \"{(i % 30) + 1}\") {{ id name price }}" for i in range(k // 3))
        add("wide_report", "wide_report", "{ " + sel + " }", param=k, heavy=True)
    for _ in range(n):  # many aliases (still far below flood range)
        k = rng.randint(15, 30)
        sel = " ".join(f'u{i}: user(id: "{rng.randint(1, 200)}") {{ id name }}' for i in range(k))
        add("alias_batch_ui", "alias_batch_ui", "{ " + sel + " }", param=k, heavy=True)
    if P["extra_benign"]:
        for _ in range(n):  # readable aliases, inline fragments, directives on variables
            i = rng.randint(1, 200)
            q, v = rng.choice([
                (f'{{ owner: user(id: "{i}") {{ displayName: name handle: username }} backup: user(id: "{(i % 200) + 1}") {{ name }} }}', None),
                ("query($on: Boolean!) { me { id name @include(if: $on) email @include(if: $on) } }", {"on": True}),
                (f'{{ posts(first: 3) {{ ... on Post {{ id title author {{ name }} }} }} u: user(id: "{i}") {{ id }} }}', None)])
            add("aliased_readable", "aliased_readable", q, v)
        for _ in range(n):  # wide pages and a result tree after a mutation
            add("wide_page", "wide_page", rng.choice([
                f"{{ users(first: {rng.choice([50, 100, 150])}) {{ id name username }} }}",
                f"{{ products(first: 30) {{ id name price stock }} posts(first: {rng.choice([20, 50])}) {{ id title }} }}",
                'mutation { login(email: "a@example.test", password: "pw") { token user { id name friends(first: 3) { name } } } }']),
                heavy=True)
    return items


def build(profile: str = "dev") -> Dict[str, Any]:
    P = PROFILES[profile]
    rng = random.Random(P["seed"])
    attacks = gen_attacks(rng, P)
    benign = gen_benign(rng, P)
    items = attacks + benign
    for i, it in enumerate(items):
        it["id"] = f"{it['label'][0]}{i:04d}"
    return {
        "profile": profile, "seed": P["seed"], "attack_work_min": ATTACK_WORK_MIN, "benign_work_max": BENIGN_WORK_MAX,
        "owasp": OWASP, "attack_classes": ATTACKS, "items": items,
    }


def out_path(profile: str) -> Path:
    return Path(__file__).with_name("corpus.json" if profile == "dev" else f"corpus-{profile}.json")


if __name__ == "__main__":
    import sys
    prof = sys.argv[1] if len(sys.argv) > 1 else "dev"
    corpus = build(prof)
    OUT = out_path(prof)
    OUT.write_text(json.dumps(corpus, indent=None, separators=(",", ":")), encoding="utf-8")
    atk = [i for i in corpus["items"] if i["label"] == "attack"]
    ben = [i for i in corpus["items"] if i["label"] == "benign"]
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB): {len(atk)} attacks, {len(ben)} benign")
    by: Dict[str, int] = {}
    for it in atk:
        by[it["cls"]] = by.get(it["cls"], 0) + 1
    print(by)
