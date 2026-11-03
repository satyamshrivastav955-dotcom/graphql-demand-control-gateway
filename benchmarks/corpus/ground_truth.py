"""Exact work counter for operations against the demo upstream, independent of Sentinel's analyzer.

"Work" is the number of field resolutions the demo upstream's executor performs for an operation (the same quantity
its work-budget fuse counts). It is computed over the real in-memory data with memoisation, so even operations whose
execution would take 10^12 resolutions are counted in milliseconds. This is the ground truth used to label the
work-amplification attack classes, and it is cross-checked against real execution in the test-suite.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from graphql import parse
from graphql.language import ast as A

from demo.upstream import app as demo

LIST_FIELDS = {("User", "friends"): "_friends", ("User", "posts"): "_posts",
               ("Post", "comments"): "_comments", ("Comment", "replies"): "_replies"}
OBJECT_FIELDS = {("Post", "author"): "author", ("Comment", "author"): "author"}
CAP = 10 ** 15  # report "at least this much" for astronomically large operations


class WorkCounter:
    def __init__(self, query: str, variables: Optional[dict] = None, operation_name: Optional[str] = None):
        doc = parse(query)
        self.fragments = {d.name.value: d for d in doc.definitions if isinstance(d, A.FragmentDefinitionNode)}
        ops = [d for d in doc.definitions if isinstance(d, A.OperationDefinitionNode)]
        self.op = next((o for o in ops if o.name and o.name.value == operation_name), ops[0]) if operation_name else ops[0]
        self.variables = variables or {}
        self.memo: Dict[tuple, int] = {}
        self.schema = demo.schema

    # -- selection handling ---------------------------------------------------------------------------------------
    def _truthy(self, node: A.DirectiveNode) -> Optional[bool]:
        arg = node.arguments[0].value if node.arguments else None
        if isinstance(arg, A.BooleanValueNode):
            return arg.value
        if isinstance(arg, A.VariableNode):
            return bool(self.variables.get(arg.name.value))
        return None

    def _included(self, node) -> bool:
        for d in node.directives or ():
            v = self._truthy(d)
            if d.name.value == "skip" and v:
                return False
            if d.name.value == "include" and v is False:
                return False
        return True

    def _collect(self, sets: List[A.SelectionSetNode], seen: Optional[set] = None) -> Dict[str, List[A.FieldNode]]:
        groups: Dict[str, List[A.FieldNode]] = {}
        seen = set() if seen is None else seen
        for ss in sets:
            for sel in ss.selections:
                if not self._included(sel):
                    continue
                if isinstance(sel, A.FieldNode):
                    groups.setdefault(sel.alias.value if sel.alias else sel.name.value, []).append(sel)
                elif isinstance(sel, A.FragmentSpreadNode):
                    if sel.name.value in seen:
                        continue
                    seen.add(sel.name.value)
                    frag = self.fragments[sel.name.value]
                    for k, v in self._collect([frag.selection_set], seen).items():
                        groups.setdefault(k, []).extend(v)
                elif isinstance(sel, A.InlineFragmentNode):
                    for k, v in self._collect([sel.selection_set], seen).items():
                        groups.setdefault(k, []).extend(v)
        return groups

    def _first(self, node: A.FieldNode) -> int:
        for arg in node.arguments or ():
            if arg.name.value == "first":
                v = arg.value
                if isinstance(v, A.IntValueNode):
                    n = int(v.value)
                elif isinstance(v, A.VariableNode):
                    n = int(self.variables.get(v.name.value, 10))
                else:
                    n = 10
                return max(0, min(n, 1000))
        return 10

    # -- counting -------------------------------------------------------------------------------------------------
    def count_object(self, sets: List[A.SelectionSetNode], typename: str, obj: Optional[dict]) -> int:
        key = (tuple(id(s) for s in sets), typename, id(obj))
        if key in self.memo:
            return self.memo[key]
        total = 0
        for fnodes in self._collect(sets).values():
            f = fnodes[0]
            name = f.name.value
            total += 1
            if name == "__typename" or obj is None:
                continue
            subsets = [n.selection_set for n in fnodes if n.selection_set]
            if (typename, name) in LIST_FIELDS:
                for item in obj[LIST_FIELDS[(typename, name)]][: self._first(f)]:
                    total += self.count_object(subsets, _item_type(typename, name), item)
            elif (typename, name) in OBJECT_FIELDS:
                total += self.count_object(subsets, _item_type(typename, name), obj[OBJECT_FIELDS[(typename, name)]])
            elif typename == "AuthPayload" and name == "user":
                total += self.count_object(subsets, "User", demo.USERS["1"])
            if total >= CAP:
                total = CAP
                break
        self.memo[key] = total
        return total

    def total(self) -> int:
        ss = self.op.selection_set
        root = "Mutation" if self.op.operation.value == "mutation" else "Query"
        total = 0
        for fnodes in self._collect([ss]).values():
            f = fnodes[0]
            name = f.name.value
            subsets = [n.selection_set for n in fnodes if n.selection_set]
            total += 1
            if name == "__typename" or not subsets and name not in ("me",):
                continue
            if root == "Query":
                if name == "me":
                    total += self.count_object(subsets, "User", demo.USERS["1"]) if subsets else 0
                elif name == "user":
                    u = demo.USERS.get(_arg(f, "id", self.variables))
                    total += self.count_object(subsets, "User", u) if u else 0
                elif name == "users":
                    for u in list(demo.USERS.values())[: self._first(f)]:
                        total += self.count_object(subsets, "User", u)
                elif name == "post":
                    p = demo.POSTS.get(_arg(f, "id", self.variables))
                    total += self.count_object(subsets, "Post", p) if p else 0
                elif name == "posts":
                    for p in list(demo.POSTS.values())[: self._first(f)]:
                        total += self.count_object(subsets, "Post", p)
                elif name == "product":
                    total += len(self._collect(subsets)) if _arg(f, "id", self.variables) in demo.PRODUCTS else 0
                elif name == "products":
                    total += min(self._first(f), len(demo.PRODUCTS)) * len(self._collect(subsets))
            else:
                if name == "login":
                    total += self.count_object(subsets, "AuthPayload", {})
                elif name == "createPost":
                    post = {"author": demo.USERS["1"], "_comments": []}
                    total += self.count_object(subsets, "Post", post)
            if total >= CAP:
                return CAP
        return min(total, CAP)


def _arg(node: A.FieldNode, name: str, variables: dict) -> Optional[str]:
    for a in node.arguments or ():
        if a.name.value == name:
            if isinstance(a.value, A.StringValueNode):
                return a.value.value
            if isinstance(a.value, A.VariableNode):
                v = variables.get(a.value.name.value)
                return None if v is None else str(v)
    return None


def _item_type(parent: str, field: str) -> str:
    t = demo.schema.type_map[parent].fields[field].type
    while hasattr(t, "of_type"):
        t = t.of_type
    return t.name


def work(query: str, variables: Optional[dict] = None, operation_name: Optional[str] = None) -> int:
    """Number of field resolutions the demo upstream performs for ``query`` (capped at 10^15)."""
    return WorkCounter(query, variables, operation_name).total()
