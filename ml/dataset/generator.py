"""Synthetic GraphQL workload generator (benign + abusive operations).

Operations are produced by random walks over a fictional e-commerce/social schema,
so they differ in shape, field choice, arguments, formatting and size rather than
being filled-in copies of a few templates. Attack parameter ranges deliberately
overlap with the heavy end of benign traffic.

Labels reflect operator *intent*: an operation is labelled abusive (1) when it
belongs to a known abuse pattern, benign (0) otherwise. See docs/evaluation.md.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# type -> (scalar fields, {relation: (target type, is_list)})
SCHEMA: Dict[str, Tuple[List[str], Dict[str, Tuple[str, bool]]]] = {
    "User": (["id", "name", "username", "email", "avatarUrl", "bio", "createdAt", "role", "followersCount"],
             {"posts": ("Post", True), "friends": ("User", True), "orders": ("Order", True),
              "profile": ("Profile", False), "comments": ("Comment", True)}),
    "Profile": (["id", "displayName", "bio", "website", "location", "timezone"], {"user": ("User", False)}),
    "Post": (["id", "title", "body", "slug", "createdAt", "viewCount", "published"],
             {"author": ("User", False), "comments": ("Comment", True), "tags": ("Tag", True),
              "category": ("Category", False)}),
    "Comment": (["id", "text", "createdAt", "likes"],
                {"author": ("User", False), "post": ("Post", False), "replies": ("Comment", True)}),
    "Tag": (["id", "name"], {"posts": ("Post", True)}),
    "Category": (["id", "name", "description"], {"posts": ("Post", True), "parent": ("Category", False)}),
    "Order": (["id", "total", "status", "createdAt"], {"user": ("User", False), "items": ("OrderItem", True)}),
    "OrderItem": (["id", "quantity", "price"], {"product": ("Product", False), "order": ("Order", False)}),
    "Product": (["id", "name", "price", "sku", "stock", "description"],
                {"reviews": ("Review", True), "category": ("Category", False)}),
    "Review": (["id", "rating", "text", "createdAt"], {"author": ("User", False), "product": ("Product", False)}),
}
ROOTS: Dict[str, Tuple[str, bool, str]] = {
    "user": ("User", False, "id"), "users": ("User", True, "first"), "post": ("Post", False, "id"),
    "posts": ("Post", True, "first"), "product": ("Product", False, "id"), "products": ("Product", True, "first"),
    "orders": ("Order", True, "first"), "me": ("User", False, ""), "category": ("Category", False, "id"),
    "comment": ("Comment", False, "id"),
}
LIST_ARG_NAMES = ("first", "limit", "take", "pageSize")


@dataclass
class F:
    name: str
    args: str = ""
    alias: str = ""
    children: Optional[List[F]] = None
    directives: str = ""
    spread: str = ""  # when set, this node is a fragment spread

    def render(self, style: Style, level: int) -> str:
        pad = style.pad(level)
        if self.spread:
            return f"{pad}...{self.spread}"
        head = f"{self.alias}: " if self.alias else ""
        head += self.name + (f"({self.args})" if self.args else "") + (f" {self.directives}" if self.directives else "")
        if not self.children:
            return pad + head
        inner = style.sep.join(c.render(style, level + 1) for c in self.children)
        return f"{pad}{head} {{{style.nl}{inner}{style.nl}{pad}}}" if style.nl else f"{head} {{ {inner} }}"


@dataclass
class Style:
    kind: str  # "pretty2", "pretty4", "compact"
    nl: str = field(init=False)
    sep: str = field(init=False)
    unit: str = field(init=False)

    def __post_init__(self):
        if self.kind == "compact":
            self.nl, self.sep, self.unit = "", " ", ""
        else:
            self.nl, self.sep, self.unit = "\n", "\n", "  " if self.kind == "pretty2" else "    "

    def pad(self, level: int) -> str:
        return self.unit * level


def random_style(rng: random.Random) -> Style:
    return Style(rng.choices(["pretty2", "pretty4", "compact"], weights=[5, 2, 3])[0])


def logint(rng: random.Random, lo: int, hi: int) -> int:
    """Log-uniform integer: many mild cases, a long tail of extreme ones."""
    import math
    return max(lo, min(hi, int(round(math.exp(rng.uniform(math.log(lo), math.log(hi)))))))


def _id_value(rng: random.Random, use_var: bool) -> str:
    if use_var:
        return "$id"
    return rng.choice([f'"{rng.choice("uvpc")}_{rng.randint(1, 99999)}"', str(rng.randint(1, 99999))])


def _scalars(rng: random.Random, typ: str, lo: int, hi: int) -> List[F]:
    pool = SCHEMA[typ][0]
    k = max(1, min(len(pool), rng.randint(lo, hi)))
    return [F(n) for n in rng.sample(pool, k)]


def build_tree(rng: random.Random, typ: str, depth: int, *, sc: Tuple[int, int] = (2, 5), rel: Tuple[int, int] = (1, 2),
               first: Tuple[int, int] = (5, 50), arg_name: Optional[str] = None, branch_prob: float = 0.8) -> List[F]:
    """Selection set for ``typ`` with ``depth`` levels of nesting (>= 1)."""
    nodes = _scalars(rng, typ, *sc)
    if depth > 1:
        relations = list(SCHEMA[typ][1].items())
        n_rel = min(len(relations), rng.randint(*rel)) if rng.random() < branch_prob else 1
        for name, (target, is_list) in rng.sample(relations, n_rel):
            args = f"{arg_name or rng.choice(LIST_ARG_NAMES)}: {rng.randint(*first)}" if is_list and rng.random() < 0.8 else ""
            nodes.append(F(name, args, children=build_tree(rng, target, depth - 1, sc=sc, rel=rel, first=first,
                                                          arg_name=arg_name, branch_prob=branch_prob * 0.7)))
    return nodes


def spine_tree(rng: random.Random, typ: str, depth: int, *, first: Optional[Tuple[int, int]] = None,
               leaf: Tuple[int, int] = (1, 1)) -> List[F]:
    """A (mostly) single chain of relations reaching exactly ``depth`` levels."""
    if depth <= 1:
        return _scalars(rng, typ, *leaf)
    name, (target, is_list) = rng.choice(list(SCHEMA[typ][1].items()))
    args = f"first: {rng.randint(*first)}" if first and is_list else ""
    nodes = _scalars(rng, typ, 1, 1)
    nodes.append(F(name, args, children=spine_tree(rng, target, depth - 1, first=first, leaf=leaf)))
    return nodes


def root_field(rng: random.Random, root: Optional[str] = None, *, use_var: bool = False,
               children: Optional[List[F]] = None, alias: str = "", first: Tuple[int, int] = (5, 50)) -> Tuple[F, str]:
    name = root or rng.choice(list(ROOTS))
    typ, is_list, arg_kind = ROOTS[name]
    args = ""
    if arg_kind == "id":
        args = f"id: {_id_value(rng, use_var)}"
    elif arg_kind == "first":
        args = f"{rng.choice(LIST_ARG_NAMES)}: {rng.randint(*first)}"
    return F(name, args, alias=alias, children=children), typ


def render_operation(rng: random.Random, roots: List[F], *, kind: str = "query", name: Optional[str] = None,
                     variables: str = "", fragments: str = "", style: Optional[Style] = None) -> str:
    style = style or random_style(rng)
    if name is None and rng.random() < 0.6:
        name = rng.choice(["GetData", "Load", "Page", "Fetch", "Q", "Dashboard", "View"]) + str(rng.randint(1, 99))
    head = kind + (f" {name}" if name else "") + (f"({variables})" if variables else "")
    if not name and not variables and kind == "query" and rng.random() < 0.3:
        head = ""
    body = style.sep.join(r.render(style, 1) for r in roots)
    op = f"{head} {{{style.nl}{body}{style.nl}}}" if style.nl else f"{head} {{ {body} }}".lstrip()
    return op + (("\n" if style.nl else " ") + fragments if fragments else "")


# --------------------------------------------------------------------------------------
# Benign categories
# --------------------------------------------------------------------------------------
def b_lookup(rng):
    var = rng.random() < 0.4
    f, typ = root_field(rng, rng.choice(["user", "post", "product", "me", "category"]), use_var=var)
    f.children = build_tree(rng, typ, rng.randint(1, 3), sc=(2, 6), rel=(1, 1))
    return render_operation(rng, [f], variables="$id: ID!" if var and f.args else "")


def b_list_page(rng):
    f, typ = root_field(rng, rng.choice(["users", "posts", "products", "orders"]), first=(5, 100))
    f.children = build_tree(rng, typ, rng.randint(2, 4), sc=(2, 5), rel=(1, 2), first=(3, 15))
    return render_operation(rng, [f])


def b_nested_view(rng):
    f, typ = root_field(rng, rng.choice(["user", "post", "product"]))
    f.children = build_tree(rng, typ, rng.randint(3, 9), sc=(2, 4), rel=(1, 2), first=(3, 12))
    return render_operation(rng, [f])


def b_dashboard(rng):
    roots = []
    for _ in range(logint(rng, 2, 14)):
        alias = f"{rng.choice(['recent', 'top', 'my', 'featured', 'latest'])}{rng.choice(['Posts', 'Users', 'Orders', 'Items'])}{rng.randint(1, 9)}" \
            if rng.random() < 0.6 else ""
        f, typ = root_field(rng, rng.choice(["users", "posts", "products", "orders"]), alias=alias, first=(3, 25))
        f.children = build_tree(rng, typ, rng.randint(1, 3), sc=(2, 5), rel=(1, 1), first=(3, 15))
        roots.append(f)
    seen = set()
    for r in roots:  # keep response keys unique to stay valid
        key = r.alias or r.name
        if key in seen:
            r.alias = f"{key}{len(seen)}"
        seen.add(r.alias or r.name)
    return render_operation(rng, roots)


def b_fragment_reuse(rng):
    typ = rng.choice(["User", "Post", "Product"])
    root = {"User": "users", "Post": "posts", "Product": "products"}[typ]
    n_frag = logint(rng, 1, 7)
    frags, spreads = [], []
    for i in range(n_frag):
        name = f"{typ}Fields{i}"
        body = "\n".join("  " + n.name for n in _scalars(rng, typ, 2, 5))
        frags.append(f"fragment {name} on {typ} {{\n{body}\n}}")
        spreads.append(F("", spread=name))
    roots = []
    for j in range(rng.randint(1, 4)):
        f, _ = root_field(rng, root, alias=f"list{j}" if j else "", first=(5, 30))
        f.children = list(spreads) + _scalars(rng, typ, 0 + 1, 2)
        roots.append(f)
    return render_operation(rng, roots, fragments="\n".join(frags), style=Style("pretty2"))


def b_mutation(rng):
    kind = rng.choice(["createPost", "addComment", "updateProfile", "placeOrder", "likePost"])
    args = {"createPost": f'title: "Post {rng.randint(1, 999)}", body: "Hello world"',
            "addComment": f'postId: "p_{rng.randint(1, 9999)}", text: "Nice one"',
            "updateProfile": f'displayName: "User{rng.randint(1, 999)}", bio: "Bio {rng.randint(1, 99)}"',
            "placeOrder": f'productId: "pr_{rng.randint(1, 9999)}", quantity: {rng.randint(1, 5)}',
            "likePost": f'id: "p_{rng.randint(1, 9999)}"'}[kind]
    out = rng.sample(["id", "createdAt", "title", "status", "likes", "total"], rng.randint(1, 3))
    return render_operation(rng, [F(kind, args, children=[F(n) for n in out])], kind="mutation")


def b_login(rng):
    args = f'email: "user{rng.randint(1, 9999)}@example.com", password: "{"x" * rng.randint(6, 14)}"'
    out = rng.sample(["token", "refreshToken", "expiresIn"], rng.randint(1, 3))
    user = [F("user", children=[F(n) for n in rng.sample(["id", "name", "role"], rng.randint(1, 3))])] if rng.random() < 0.6 else []
    return render_operation(rng, [F("login", args, children=[F(n) for n in out] + user)], kind="mutation")


def b_heavy_report(rng):
    f, typ = root_field(rng, rng.choice(["users", "orders", "products", "posts"]), first=(10, 50))
    f.children = build_tree(rng, typ, rng.randint(3, 8), sc=(5, 9), rel=(2, 3), first=(3, 12), branch_prob=0.95)
    return render_operation(rng, [f])


def b_typename(rng):
    f, typ = root_field(rng, rng.choice(["user", "post", "product", "posts"]))
    def add(nodes):
        for n in nodes:
            if n.children:
                add(n.children)
        nodes.append(F("__typename"))
    f.children = build_tree(rng, typ, rng.randint(2, 4), sc=(2, 4), rel=(1, 2))
    add(f.children)
    return render_operation(rng, [f])


def b_variables(rng):
    f, typ = root_field(rng, rng.choice(["posts", "users", "products"]), first=(10, 50))
    f.args = "first: $first, after: $cursor"
    f.children = build_tree(rng, typ, rng.randint(2, 4), sc=(2, 5), rel=(1, 2))
    return render_operation(rng, [f], variables="$first: Int = 20, $cursor: String")


def b_conditional(rng):
    f, typ = root_field(rng, rng.choice(["users", "posts", "products"]), first=(5, 30))
    pool = SCHEMA[typ][0]
    d = rng.choice(["@include(if: $withDetails)", "@skip(if: $compact)"])
    var = "$withDetails: Boolean = true" if "withDetails" in d else "$compact: Boolean = false"
    f.children = [F(n) for n in rng.sample(pool, 2)] + [F(rng.choice(pool), directives=d) for _ in range(logint(rng, 1, 12))]
    return render_operation(rng, [f], variables=var)


def b_full_profile(rng):
    typ = rng.choice(["User", "Product", "Order", "Post"])
    root = {"User": "user", "Product": "product", "Order": "orders", "Post": "post"}[typ]
    f, _ = root_field(rng, root, first=(5, 20))

    def wide(t, depth):
        nodes = [F(n) for n in SCHEMA[t][0]]
        if depth > 1:
            for name, (target, is_list) in list(SCHEMA[t][1].items())[: rng.randint(2, 4)]:
                nodes.append(F(name, f"first: {rng.choice([5, 10, 20])}" if is_list else "", children=wide(target, depth - 1)))
        return nodes
    f.children = wide(typ, rng.randint(1, 3))
    return render_operation(rng, [f])


# --------------------------------------------------------------------------------------
# Abusive categories
# --------------------------------------------------------------------------------------
def a_deep_nesting(rng):
    f, typ = root_field(rng, rng.choice(["user", "post", "category", "comment"]))
    f.children = spine_tree(rng, typ, logint(rng, 6, 35) - 1)
    return render_operation(rng, [f])


def a_alias_batching(rng):
    n = logint(rng, 6, 250)
    field_name = rng.choice(["user", "post", "product"])
    roots = [root_field(rng, field_name, alias=f"a{i}", children=_scalars(rng, ROOTS[field_name][0], 1, 3))[0]
             for i in range(n)]
    return render_operation(rng, roots)


def a_field_duplication(rng):
    typ = rng.choice(["User", "Post", "Product"])
    root = {"User": "users", "Post": "posts", "Product": "products"}[typ]
    f, _ = root_field(rng, root, first=(1, 10))
    name = rng.choice(SCHEMA[typ][0])
    f.children = [F(name) for _ in range(logint(rng, 6, 400))]
    return render_operation(rng, [f])


_WORDS = ["Core", "Base", "Meta", "Info", "Card", "Row", "Item", "Part", "Slice", "View", "Chunk", "Block"]


def _frag_names(rng, n):
    base = rng.choice(_WORDS)
    style = rng.choice(["{b}{i}", "{b}_{i}", "{b}Level{i}", "f{i}{b}"])
    return [style.format(b=base, i=i) for i in range(n)]


def a_fragment_bomb(rng):
    typ = rng.choice(["User", "Post", "Product", "Comment", "Order"])
    levels = rng.randint(4, 14)
    names = _frag_names(rng, levels + 1)
    frags = []
    for i in range(levels):
        parts = [n.name for n in _scalars(rng, typ, 1, 3)]
        parts += [f"...{names[i + 1]}" for _ in range(rng.choice([2, 2, 3, 4]))]
        rng.shuffle(parts)
        frags.append(f"fragment {names[i]} on {typ} {{ {' '.join(parts)} }}")
    frags.append(f"fragment {names[levels]} on {typ} {{ {' '.join(n.name for n in _scalars(rng, typ, 1, 4))} }}")
    root = {"User": "users", "Post": "posts", "Product": "products", "Comment": "comment", "Order": "orders"}[typ]
    f, _ = root_field(rng, root, first=(1, 10))
    f.children = [F("", spread=names[0])] + ([F(rng.choice(SCHEMA[typ][0]))] if rng.random() < 0.5 else [])
    return render_operation(rng, [f], fragments="\n".join(frags))


_SELF_REL = {"User": "friends", "Comment": "replies", "Category": "parent"}


def a_fragment_depth(rng):
    typ = rng.choice(list(_SELF_REL))
    rel = _SELF_REL[typ]
    levels = rng.randint(7, 25)
    names = _frag_names(rng, levels + 1)
    frags = []
    for i in range(levels):
        extra = [n.name for n in _scalars(rng, typ, 0 + (rng.random() < 0.5), 2)] if rng.random() < 0.7 else []
        frags.append(f"fragment {names[i]} on {typ} {{ {' '.join(extra)} {rel} {{ ...{names[i + 1]} }} }}")
    frags.append(f"fragment {names[levels]} on {typ} {{ {' '.join(n.name for n in _scalars(rng, typ, 1, 3))} }}")
    root = {"User": "user", "Comment": "comment", "Category": "category"}[typ]
    f, _ = root_field(rng, root)
    f.children = [F("", spread=names[0])]
    return render_operation(rng, [f], fragments="\n".join(frags))


def a_directive_overload(rng):
    n = logint(rng, 5, 60)
    f, typ = root_field(rng, rng.choice(["users", "posts"]), first=(1, 10))
    d = rng.choice(["@include(if: true)", "@skip(if: false)", "@include(if: $flag)"])
    pool = SCHEMA[typ][0]
    f.children = [F(rng.choice(pool), alias=f"f{i}", directives=d) for i in range(n)]
    return render_operation(rng, [f], variables="$flag: Boolean = true" if "$flag" in d else "")


def a_introspection(rng):
    def pick(options, lo=1):
        return " ".join(rng.sample(options, rng.randint(lo, len(options))))
    type_ref = "{ name kind %s }" % ("ofType { name kind %s }" % ("ofType { name kind }" if rng.random() < 0.5 else "")
                                      if rng.random() < 0.6 else "")
    field_sel = pick(["name", "description", "isDeprecated", "args { name type " + type_ref + " }",
                      "type " + type_ref])
    type_sel = pick(["kind", "name", "description", "fields { " + field_sel + " }", "interfaces { name }",
                     "possibleTypes { name }", "enumValues { name }", "inputFields { name }"])
    if rng.random() < 0.35:
        t = rng.choice(list(SCHEMA))
        body = f'__type(name: "{t}") {{ {type_sel} }}'
    else:
        body = "__schema { " + pick(["queryType { name }", "mutationType { name }", "subscriptionType { name }",
                                      "types { " + type_sel + " }", "directives { name locations args { name } }"]) + " }"
    op = rng.choice(["", "query IntrospectionQuery ", "query "])
    return f"{op}{{ {body} }}".strip()


def a_sensitive_enum(rng):
    n = logint(rng, 3, 80)
    sens = rng.sample(["email", "role", "bio"], rng.randint(1, 2)) + rng.sample(["password", "token", "ssn", "secret", "apiKey"], rng.randint(1, 3))
    roots = []
    for i in range(n):
        roots.append(F("user", f'id: {rng.randint(1, 99999)}', alias=f"u{i}", children=[F("id")] + [F(s) for s in sens]))
    return render_operation(rng, roots)


def a_list_amplification(rng):
    f, typ = root_field(rng, rng.choice(["users", "posts", "products"]), first=(100, 1000))
    f.children = build_tree(rng, typ, rng.randint(2, 6), sc=(1, 3), rel=(1, 1), first=(100, 1000), branch_prob=0.3)
    return render_operation(rng, [f])


def a_credential_stuffing(rng):
    n = logint(rng, 3, 120)
    roots = [F("login", f'email: "victim{i}@example.com", password: "{rng.choice(["123456", "password", "qwerty", "letmein"])}{i}"',
               alias=f"try{i}", children=[F("token")]) for i in range(n)]
    return render_operation(rng, roots, kind="mutation")


def a_wide_selection(rng):
    typ = rng.choice(["User", "Product", "Order", "Post"])
    root = {"User": "users", "Product": "products", "Order": "orders", "Post": "posts"}[typ]
    f, _ = root_field(rng, root, first=(20, 300))
    def wide(t, depth):
        nodes = [F(n) for n in SCHEMA[t][0]]
        if depth > 1:
            for name, (target, is_list) in SCHEMA[t][1].items():
                nodes.append(F(name, f"first: {rng.choice([20, 50, 100])}" if is_list else "", children=wide(target, depth - 1)))
        return nodes
    f.children = wide(typ, rng.randint(2, 3))
    return render_operation(rng, [f])


@dataclass(frozen=True)
class Category:
    name: str
    label: int
    build: Callable[[random.Random], str]


CATEGORIES: List[Category] = [
    Category("lookup", 0, b_lookup), Category("list_page", 0, b_list_page), Category("nested_view", 0, b_nested_view),
    Category("dashboard", 0, b_dashboard), Category("fragment_reuse", 0, b_fragment_reuse),
    Category("mutation", 0, b_mutation), Category("login", 0, b_login), Category("heavy_report", 0, b_heavy_report),
    Category("typename", 0, b_typename), Category("variables", 0, b_variables),
    Category("conditional_fields", 0, b_conditional), Category("full_profile", 0, b_full_profile),
    Category("deep_nesting", 1, a_deep_nesting), Category("alias_batching", 1, a_alias_batching),
    Category("field_duplication", 1, a_field_duplication), Category("fragment_bomb", 1, a_fragment_bomb),
    Category("fragment_depth", 1, a_fragment_depth), Category("directive_overload", 1, a_directive_overload),
    Category("introspection", 1, a_introspection), Category("sensitive_enumeration", 1, a_sensitive_enum),
    Category("list_amplification", 1, a_list_amplification), Category("credential_stuffing", 1, a_credential_stuffing),
    Category("wide_selection", 1, a_wide_selection),
]


def generate(category: Category, n: int, seed: int) -> List[str]:
    rng = random.Random(f"{seed}:{category.name}")
    return [category.build(rng) for _ in range(n)]
