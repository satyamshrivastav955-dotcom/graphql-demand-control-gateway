"""Schema-aware, federation-aware static cost estimation.

Loads an SDL (a plain schema, a federation subgraph schema, or a composed *supergraph* schema) and estimates the
cost of an operation before it executes, following the same model as Apollo Router demand control and the IBM
GraphQL cost-directive proposal:

* a field whose type is an object/interface/union costs 1, a scalar or enum costs 0 (``@cost(weight: n)`` overrides);
* a list field multiplies the cost of everything below it by the list size, taken from ``@listSize`` (the value of
  a slicing argument such as ``first``, else ``assumedSize``) and otherwise the configured default;
* a mutation adds a base cost.

On a supergraph the estimate is also attributed to the subgraphs that own each field (``@join__field`` /
``@join__type``), so a per-subgraph budget can be enforced the way Router 2.12 does. Fragments are memoised, so
fragment bombs are costed in linear time. Fields that do not exist in the schema are reported (probing / typos).

Estimates are upper bounds that ignore ``@skip``/``@include`` on variables and sum all branches of an abstract type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from graphql import (
    GraphQLField,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLSchema,
    build_ast_schema,
    get_named_type,
    is_composite_type,
    parse,
)
from graphql.language import ast as A

MAX_COST = 10 ** 12
MUTATION_BASE_COST = 10


@dataclass
class CostResult:
    total: int = 0
    by_subgraph: Dict[str, int] = field(default_factory=dict)
    by_root_field: Dict[str, int] = field(default_factory=dict)
    unknown_fields: List[str] = field(default_factory=list)

    def top_contributors(self, n: int = 3) -> List[Tuple[str, int]]:
        return sorted(self.by_root_field.items(), key=lambda kv: kv[1], reverse=True)[:n]


@dataclass
class _Rel:
    """Cost of a selection set relative to being executed once."""
    total: int = 0
    sub: Dict[str, int] = field(default_factory=dict)

    def add(self, other: _Rel, mult: int = 1) -> None:
        self.total = min(MAX_COST, self.total + other.total * mult)
        for g, c in other.sub.items():
            self.sub[g] = min(MAX_COST, self.sub.get(g, 0) + c * mult)

    def scaled(self, mult: int) -> _Rel:
        r = _Rel()
        r.add(self, mult)
        return r


def _directive(node: Optional[A.Node], name: str) -> Optional[A.DirectiveNode]:
    for d in getattr(node, "directives", None) or ():
        if d.name.value == name:
            return d
    return None


def _const(node: A.ValueNode) -> Any:
    if isinstance(node, A.IntValueNode):
        return int(node.value)
    if isinstance(node, A.StringValueNode):
        return node.value
    if isinstance(node, A.EnumValueNode):
        return node.value
    if isinstance(node, A.ListValueNode):
        return [_const(v) for v in node.values]
    if isinstance(node, A.BooleanValueNode):
        return node.value
    return None


def _args(d: Optional[A.DirectiveNode]) -> Dict[str, Any]:
    return {a.name.value: _const(a.value) for a in (d.arguments if d else ())}


class SchemaCost:
    def __init__(self, sdl: str, default_list_size: int = 10):
        self.default_list_size = default_list_size
        self.schema: GraphQLSchema = build_ast_schema(parse(sdl), assume_valid_sdl=True)
        self.graph_names: Dict[str, str] = {}      # join__Graph enum value -> subgraph name
        self._read_graphs(sdl)
        self.federated = bool(self.graph_names)

    # -- construction ----------------------------------------------------------------------------------------------
    @classmethod
    def from_file(cls, path: str, default_list_size: int = 10) -> SchemaCost:
        with open(path, encoding="utf-8") as fh:
            return cls(fh.read(), default_list_size)

    def _read_graphs(self, sdl: str) -> None:
        enum = self.schema.type_map.get("join__Graph")
        if enum is None or not hasattr(enum, "values"):
            return
        for value_name, value in enum.values.items():
            d = _directive(value.ast_node, "join__graph")
            self.graph_names[value_name] = str(_args(d).get("name") or value_name.lower())

    # -- schema introspection helpers -------------------------------------------------------------------------------
    def _owner(self, parent: Any, fld: GraphQLField) -> Optional[str]:
        """Subgraph that resolves ``parent.fld`` (first owner when several can)."""
        if not self.federated:
            return None
        graphs: List[str] = []
        for d in getattr(fld.ast_node, "directives", None) or ():
            if d.name.value == "join__field":
                g = _args(d).get("graph")
                if g:
                    graphs.append(g)
        if not graphs:
            for d in getattr(parent.ast_node, "directives", None) or ():
                if d.name.value == "join__type":
                    g = _args(d).get("graph")
                    if g:
                        graphs.append(g)
        return self.graph_names.get(graphs[0], graphs[0]) if graphs else None

    def _field_weight(self, fld: GraphQLField) -> int:
        d = _directive(fld.ast_node, "cost")
        if d is not None:
            w = _args(d).get("weight")
            try:
                return max(0, int(w))
            except (TypeError, ValueError):
                pass
        named = get_named_type(fld.type)
        if is_composite_type(named):
            td = _directive(getattr(named, "ast_node", None), "cost")
            if td is not None:
                try:
                    return max(0, int(_args(td).get("weight")))
                except (TypeError, ValueError):
                    pass
            return 1
        return 0

    @staticmethod
    def _is_list(t: Any) -> bool:
        while isinstance(t, GraphQLNonNull):
            t = t.of_type
        return isinstance(t, GraphQLList)

    # -- estimation -------------------------------------------------------------------------------------------------
    def estimate(self, document: A.DocumentNode, operation: A.OperationDefinitionNode,
                 variables: Optional[dict] = None) -> CostResult:
        est = _Estimator(self, document, operation, variables or {})
        return est.run()


class _Estimator:
    def __init__(self, sc: SchemaCost, document: A.DocumentNode, op: A.OperationDefinitionNode, variables: dict):
        self.sc = sc
        self.op = op
        self.fragments = {d.name.value: d for d in document.definitions if isinstance(d, A.FragmentDefinitionNode)}
        self.var_defaults = {v.variable.name.value: _const(v.default_value) for v in (op.variable_definitions or ())
                             if v.default_value is not None}
        self.variables = variables
        self.memo: Dict[Tuple[str, str], _Rel] = {}
        self.in_progress: set = set()
        self.unknown: List[str] = []

    def _skipped(self, node: Any) -> bool:
        for d in node.directives or ():
            if d.name.value in ("skip", "include") and d.arguments:
                v = d.arguments[0].value
                if isinstance(v, A.BooleanValueNode):
                    if (d.name.value == "skip") == v.value:
                        return True
        return False

    def _int(self, value: A.ValueNode) -> Optional[int]:
        if isinstance(value, A.IntValueNode):
            return int(value.value)
        if isinstance(value, A.VariableNode):
            v = self.variables.get(value.name.value, self.var_defaults.get(value.name.value))
            if isinstance(v, int) and not isinstance(v, bool):
                return v
        return None

    def _list_size(self, fld: GraphQLField, node: A.FieldNode) -> int:
        d = _directive(fld.ast_node, "listSize")
        if d is None:
            return self.sc.default_list_size
        a = _args(d)
        sizes: List[int] = []
        for sa in a.get("slicingArguments") or ():
            for arg in node.arguments or ():
                if arg.name.value == sa:
                    n = self._int(arg.value)
                    if n is not None:
                        sizes.append(max(0, n))
        if sizes:
            return max(sizes)
        if a.get("assumedSize") is not None:
            return max(0, int(a["assumedSize"]))
        return self.sc.default_list_size

    def selection(self, ss: Optional[A.SelectionSetNode], parent: Any) -> _Rel:
        rel = _Rel()
        if ss is None:
            return rel
        for sel in ss.selections:
            if self._skipped(sel):
                continue
            if isinstance(sel, A.FieldNode):
                self.field(sel, parent, rel)
            elif isinstance(sel, A.FragmentSpreadNode):
                frag = self.fragments.get(sel.name.value)
                if frag is None:
                    continue
                tc = self.sc.schema.type_map.get(frag.type_condition.name.value, parent)
                rel.add(self.fragment(sel.name.value, tc))
            elif isinstance(sel, A.InlineFragmentNode):
                tc = parent
                if sel.type_condition:
                    tc = self.sc.schema.type_map.get(sel.type_condition.name.value, parent)
                rel.add(self.selection(sel.selection_set, tc))
        return rel

    def fragment(self, name: str, parent: Any) -> _Rel:
        key = (name, getattr(parent, "name", ""))
        if key in self.memo:
            return self.memo[key]
        if key in self.in_progress:
            return _Rel()
        self.in_progress.add(key)
        rel = self.selection(self.fragments[name].selection_set, parent)
        self.in_progress.discard(key)
        self.memo[key] = rel
        return rel

    def field(self, node: A.FieldNode, parent: Any, into: _Rel) -> Optional[_Rel]:
        name = node.name.value
        if name.startswith("__"):
            return None  # introspection and __typename are costed by their own rule
        fields = getattr(parent, "fields", None)
        fld = fields.get(name) if fields else None
        if fld is None:
            if isinstance(parent, (GraphQLObjectType, GraphQLInterfaceType)):
                self.unknown.append(f"{parent.name}.{name}")
            return None
        own_weight = self.sc._field_weight(fld)
        owner = self.sc._owner(parent, fld)
        is_list = self.sc._is_list(fld.type)
        size = self._list_size(fld, node) if is_list else 1
        child_parent = get_named_type(fld.type)
        child = self.selection(node.selection_set, child_parent) if node.selection_set else _Rel()
        # cost of one element: the field's own weight plus everything selected below it
        elem = _Rel(total=own_weight, sub={owner: own_weight} if owner and own_weight else {})
        elem.add(child)
        result = elem.scaled(size)
        into.add(result)
        return result

    def run(self) -> CostResult:
        sc = self.sc
        op_type = self.op.operation.value
        root = {"query": sc.schema.query_type, "mutation": sc.schema.mutation_type,
                "subscription": sc.schema.subscription_type}[op_type]
        out = CostResult()
        if root is None:
            return out
        total = _Rel()
        try:
            for sel in (self.op.selection_set.selections if self.op.selection_set else ()):
                if self._skipped(sel):
                    continue
                if isinstance(sel, A.FieldNode):
                    r = _Rel()
                    res = self.field(sel, root, r)
                    if res is not None:
                        key = sel.alias.value if sel.alias else sel.name.value
                        out.by_root_field[key] = out.by_root_field.get(key, 0) + res.total
                    total.add(r)
                else:
                    total.add(self.selection(A.SelectionSetNode(selections=(sel,)), root))
        except RecursionError:
            total = _Rel(total=MAX_COST)
        if op_type == "mutation":
            total.total = min(MAX_COST, total.total + MUTATION_BASE_COST)
        out.total = min(MAX_COST, total.total)
        out.by_subgraph = dict(total.sub)
        out.unknown_fields = self.unknown
        return out
