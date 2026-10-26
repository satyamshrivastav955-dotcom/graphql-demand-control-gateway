"""
GraphQL Query Cost & Complexity Feature Extractor.
Analyzes AST field counts, arguments, pagination multipliers (first/limit/count),
and directive-based cost annotations (@cost(weight: Int) or @complexity(value: Int)).
"""
from typing import Dict, Optional
from graphql.language.visitor import Visitor, visit
from graphql.language.ast import DocumentNode, IntValueNode, FieldNode


class CostVisitor(Visitor):
    def __init__(self, custom_field_costs: Optional[Dict[str, int]] = None):
        super().__init__()
        self.complexity = 0
        self.multiplier_stack = [1]
        self.max_multiplier = 1
        self.estimated_cost = 0
        self.custom_field_costs = custom_field_costs or {}
        self.directive_cost_count = 0

    def enter_field(self, node: FieldNode, key, parent, path, ancestors):
        current_multiplier = self.multiplier_stack[-1]
        field_name = node.name.value
        field_cost = 1
        new_multiplier = 1

        # Check directive annotations: @cost(weight: Int) or @complexity(value: Int)
        if node.directives:
            for directive in node.directives:
                d_name = directive.name.value.lower()
                if d_name in ("cost", "complexity"):
                    self.directive_cost_count += 1
                    if directive.arguments:
                        for arg in directive.arguments:
                            if arg.name.value.lower() in ("weight", "complexity", "value"):
                                if isinstance(arg.value, IntValueNode):
                                    try:
                                        val = int(arg.value.value)
                                        if val > 0:
                                            field_cost = max(field_cost, val)
                                    except ValueError:
                                        pass

        # Check custom field cost mapping if configured
        if field_name in self.custom_field_costs:
            field_cost = max(field_cost, self.custom_field_costs[field_name])

        # Analyze arguments for pagination multipliers
        if node.arguments:
            field_cost += len(node.arguments)
            for arg in node.arguments:
                arg_name = arg.name.value.lower()
                if arg_name in ("first", "limit", "count", "size", "last", "take"):
                    if isinstance(arg.value, IntValueNode):
                        try:
                            val = int(arg.value.value)
                            if val > 0:
                                new_multiplier = min(val, 1000)
                        except ValueError:
                            pass

        self.complexity += field_cost
        self.estimated_cost += field_cost * current_multiplier
        next_multiplier = min(current_multiplier * new_multiplier, 100000)
        self.multiplier_stack.append(next_multiplier)
        if next_multiplier > self.max_multiplier:
            self.max_multiplier = next_multiplier

    def leave_field(self, node: FieldNode, key, parent, path, ancestors):
        if len(self.multiplier_stack) > 1:
            self.multiplier_stack.pop()


def extract_cost_features(
    ast: DocumentNode,
    query_string: str = "",
    custom_field_costs: Optional[Dict[str, int]] = None
) -> dict:
    """Extract complexity score, pagination multipliers, directive costs, and token count from GraphQL AST."""
    visitor = CostVisitor(custom_field_costs=custom_field_costs)
    visit(ast, visitor)

    token_count = len(query_string.split()) if query_string else 0

    return {
        "complexity_score": visitor.complexity,
        "token_count": token_count,
        "cost_estimate": visitor.estimated_cost,
        "max_multiplier": visitor.max_multiplier,
        "directive_cost_count": visitor.directive_cost_count,
    }
