"""
Fragment and Directive Security Analyzer.
Detects circular fragment loops, fragment bombs, and directive overload attacks in GraphQL AST.
"""
from collections import defaultdict
from typing import Dict, Set, List
from graphql.language.visitor import Visitor, visit
from graphql.language.ast import (
    DocumentNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    FieldNode,
    InlineFragmentNode,
)


class FragmentDirectiveVisitor(Visitor):
    def __init__(self):
        super().__init__()
        self.fragments: Dict[str, Set[str]] = defaultdict(set)
        self.current_fragment = None
        self.total_directives = 0
        self.max_directives_per_field = 0
        self.fragment_spread_count = 0

    def enter_fragment_definition(self, node: FragmentDefinitionNode, *args):
        self.current_fragment = node.name.value

    def leave_fragment_definition(self, node: FragmentDefinitionNode, *args):
        self.current_fragment = None

    def enter_fragment_spread(self, node: FragmentSpreadNode, *args):
        self.fragment_spread_count += 1
        spread_name = node.name.value
        if self.current_fragment:
            self.fragments[self.current_fragment].add(spread_name)

    def enter_field(self, node: FieldNode, *args):
        if node.directives:
            d_count = len(node.directives)
            self.total_directives += d_count
            if d_count > self.max_directives_per_field:
                self.max_directives_per_field = d_count

    def enter_inline_fragment(self, node: InlineFragmentNode, *args):
        if node.directives:
            d_count = len(node.directives)
            self.total_directives += d_count


def has_cycle(graph: Dict[str, Set[str]]) -> bool:
    """Detect cycles in fragment dependency directed graph using DFS."""
    visited = set()
    rec_stack = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True

        rec_stack.remove(node)
        return False

    for node in list(graph.keys()):
        if node not in visited:
            if dfs(node):
                return True
    return False


def extract_fragment_directive_features(ast: DocumentNode) -> dict:
    """Analyze fragment graphs and directives for DoS patterns."""
    visitor = FragmentDirectiveVisitor()
    visit(ast, visitor)

    circular = 1 if has_cycle(visitor.fragments) else 0
    directive_abuse = 1 if (visitor.max_directives_per_field > 5 or visitor.total_directives > 20) else 0

    return {
        "circular_fragment_detected": circular,
        "fragment_spread_count": visitor.fragment_spread_count,
        "max_directives_per_field": visitor.max_directives_per_field,
        "directive_abuse_detected": directive_abuse,
    }
