"""Fragment-aware GraphQL operation analyzer.

Computes the structural, semantic and cost features of the operation that the
server would actually execute. Fragment spreads are resolved (with per-fragment
memoisation, so exponential "fragment bomb" documents are analysed in linear
time) and fragment cycles are detected instead of recursing forever.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from graphql import GraphQLError, parse
from graphql.language import ast as A
from graphql.language.lexer import Lexer
from graphql.language.token_kind import TokenKind

SENSITIVE_KEYWORDS = (
    "password", "passwd", "secret", "token", "ssn", "creditcard", "cardnumber",
    "apikey", "api_key", "privatekey", "otp", "email",
)
INTROSPECTION_ROOTS = ("__schema", "__type")
LIST_ARGUMENTS = ("first", "last", "limit", "take", "pagesize", "per_page", "count", "size", "top")
MAX_LIST_MULTIPLIER = 1000
MAX_COST = 10 ** 9

# Numeric features, in the fixed order used by the ML model.
FEATURE_NAMES = (
    "max_depth", "field_count", "alias_count", "fragment_count", "fragment_spread_count",
    "directive_count", "introspection_score", "sensitive_field_count", "mutation_score",
    "complexity_score", "token_count", "query_length", "duplicate_field_count",
    "max_list_multiplier", "variable_count", "operation_count",
)


class AnalysisError(Exception):
    """The document cannot be analysed (syntax error, no/ambiguous operation, ...)."""


class TooComplexToParse(AnalysisError):
    """Parsing exceeded the token or recursion budget; treated as a limit violation."""


@dataclass
class Stats:
    fields: int = 0
    depth: int = 0
    aliases: int = 0
    directives: int = 0
    intro: int = 0
    sensitive: int = 0
    dups: int = 0
    spreads: int = 0
    cost: int = 0
    max_mult: int = 1

    def add(self, other: Stats, depth_offset: int = 0, cost_mult: int = 1) -> None:
        self.fields += other.fields
        self.depth = max(self.depth, other.depth + depth_offset)
        self.aliases += other.aliases
        self.directives += other.directives
        self.intro += other.intro
        self.sensitive += other.sensitive
        self.dups += other.dups
        self.spreads += other.spreads
        self.cost = min(MAX_COST, self.cost + other.cost * cost_mult)
        self.max_mult = max(self.max_mult, other.max_mult * cost_mult)


@dataclass
class Analysis:
    features: Dict[str, float]
    operation_name: Optional[str]
    operation_type: Optional[str]
    fragment_cycle: bool = False
    unknown_fragments: List[str] = field(default_factory=list)


class _Walker:
    def __init__(self, fragments: Dict[str, A.FragmentDefinitionNode], variables: Optional[dict]):
        self.fragments = fragments
        self.variables = variables or {}
        self.memo: Dict[str, Stats] = {}
        self.in_progress: set = set()
        self.cycle = False
        self.unknown: List[str] = []

    def _int_arg(self, value: A.ValueNode) -> Optional[int]:
        if isinstance(value, A.IntValueNode):
            try:
                return int(value.value)
            except ValueError:
                return None
        if isinstance(value, A.VariableNode):
            v = self.variables.get(value.name.value)
            if isinstance(v, int) and not isinstance(v, bool):
                return v
        return None

    def _list_multiplier(self, node: A.FieldNode) -> int:
        mult = 1
        for arg in node.arguments or ():
            if arg.name.value.lower() in LIST_ARGUMENTS:
                n = self._int_arg(arg.value)
                if n is not None and n > 1:
                    mult = max(mult, min(n, MAX_LIST_MULTIPLIER))
        return mult

    def fragment(self, name: str) -> Stats:
        if name in self.memo:
            return self.memo[name]
        frag = self.fragments.get(name)
        if frag is None:
            self.unknown.append(name)
            return Stats()
        if name in self.in_progress:
            self.cycle = True
            return Stats()
        self.in_progress.add(name)
        stats = self.selection_set(frag.selection_set, 0)
        stats.directives += len(frag.directives or ())
        self.in_progress.discard(name)
        self.memo[name] = stats
        return stats

    def selection_set(self, ss: Optional[A.SelectionSetNode], depth: int) -> Stats:
        """Stats for a selection set whose fields sit at nesting level ``depth + 1``."""
        total = Stats()
        if ss is None:
            return total
        keys: Dict[str, int] = {}
        for sel in ss.selections:
            if isinstance(sel, A.FieldNode):
                name = sel.name.value
                key = sel.alias.value if sel.alias else name
                keys[key] = keys.get(key, 0) + 1
                own = Stats(fields=1, depth=depth + 1, directives=len(sel.directives or ()))
                if sel.alias:
                    own.aliases = 1
                lowered = name.lower()
                if name in INTROSPECTION_ROOTS:
                    own.intro = 1
                elif not name.startswith("__") and any(k in lowered for k in SENSITIVE_KEYWORDS):
                    own.sensitive = 1
                mult = self._list_multiplier(sel)
                own.cost = 1 + len(sel.arguments or ())
                own.max_mult = mult
                child = self.selection_set(sel.selection_set, depth + 1)
                total.add(own)
                # Children are executed once per element of this field's list.
                total.add(child, cost_mult=mult)
                total.cost = min(MAX_COST, total.cost)
            elif isinstance(sel, A.FragmentSpreadNode):
                sub = self.fragment(sel.name.value)
                spread = Stats(spreads=1, directives=len(sel.directives or ()))
                total.add(spread)
                total.add(sub, depth_offset=depth)
            elif isinstance(sel, A.InlineFragmentNode):
                total.directives += len(sel.directives or ())
                total.add(self.selection_set(sel.selection_set, depth))
        total.dups += sum(c - 1 for c in keys.values() if c > 1)
        return total


def count_tokens(query: str, limit: int) -> int:
    """Count lexer tokens, stopping once ``limit`` is exceeded."""
    lexer = Lexer(_source(query))
    n = 0
    tok = lexer.advance()
    while tok.kind != TokenKind.EOF:
        n += 1
        if n > limit:
            return n
        tok = lexer.advance()
    return n


def _source(query: str):
    from graphql.language.source import Source
    return Source(query)


def analyze(
    query: str,
    operation_name: Optional[str] = None,
    variables: Optional[dict] = None,
    max_tokens: int = 5000,
) -> Analysis:
    try:
        token_count = count_tokens(query, max_tokens)
        if token_count > max_tokens:
            raise TooComplexToParse(f"query exceeds {max_tokens} tokens")
        doc = parse(query, no_location=True, max_tokens=max_tokens + 1)
    except TooComplexToParse:
        raise
    except GraphQLError as exc:
        raise AnalysisError(f"Syntax error: {exc.message}") from None
    except RecursionError:
        raise TooComplexToParse("query nesting exceeds the parser budget") from None

    operations = [d for d in doc.definitions if isinstance(d, A.OperationDefinitionNode)]
    fragments = {d.name.value: d for d in doc.definitions if isinstance(d, A.FragmentDefinitionNode)}
    if not operations:
        raise AnalysisError("Document contains no operation")
    if operation_name:
        matches = [o for o in operations if o.name and o.name.value == operation_name]
        if not matches:
            raise AnalysisError(f"Unknown operation '{operation_name}'")
        op = matches[0]
    elif len(operations) == 1:
        op = operations[0]
    else:
        raise AnalysisError("Operation name is required when the document has several operations")

    walker = _Walker(fragments, variables)
    try:
        stats = walker.selection_set(op.selection_set, 0)
    except RecursionError:
        raise TooComplexToParse("query nesting exceeds the analysis budget") from None
    stats.directives += len(op.directives or ())

    op_type = op.operation.value
    for name in ("fields", "aliases", "directives", "intro", "sensitive", "dups", "spreads"):
        setattr(stats, name, min(MAX_COST, getattr(stats, name)))
    features: Dict[str, float] = {
        "max_depth": stats.depth,
        "field_count": stats.fields,
        "alias_count": stats.aliases,
        "fragment_count": len(fragments),
        "fragment_spread_count": stats.spreads,
        "directive_count": stats.directives,
        "introspection_score": stats.intro,
        "sensitive_field_count": stats.sensitive,
        "mutation_score": 1 if op_type == "mutation" else 0,
        "complexity_score": stats.cost,
        "token_count": token_count,
        "query_length": len(query),
        "duplicate_field_count": stats.dups,
        "max_list_multiplier": stats.max_mult,
        "variable_count": len(op.variable_definitions or ()),
        "operation_count": len(operations),
    }
    return Analysis(
        features=features,
        operation_name=op.name.value if op.name else None,
        operation_type=op_type,
        fragment_cycle=walker.cycle,
        unknown_fragments=sorted(set(walker.unknown)),
    )


def vector(features: Dict[str, Any]) -> List[float]:
    return [float(features.get(name, 0) or 0) for name in FEATURE_NAMES]
