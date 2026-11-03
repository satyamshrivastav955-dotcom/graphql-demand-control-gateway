"""Rule catalogue: every rule and hard limit with its OWASP API Security Top 10 (2023) mapping and attack class.

This is the single source of truth. Explanations returned by the engine carry ``owasp`` and ``attack_class`` taken
from here, ``docs/owasp-mapping.md`` is generated from it (``python scripts/export_owasp_mapping.py``), and a test
fails if the engine can emit a rule that is not catalogued.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple

OWASP_API_2023: Dict[str, str] = {
    "API1": "Broken Object Level Authorization",
    "API2": "Broken Authentication",
    "API3": "Broken Object Property Level Authorization",
    "API4": "Unrestricted Resource Consumption",
    "API5": "Broken Function Level Authorization",
    "API6": "Unrestricted Access to Sensitive Business Flows",
    "API7": "Server Side Request Forgery",
    "API8": "Security Misconfiguration",
    "API9": "Improper Inventory Management",
    "API10": "Unsafe Consumption of APIs",
}


@dataclass(frozen=True)
class RuleInfo:
    id: str
    title: str
    owasp: Tuple[str, ...]
    attack_class: str
    kind: str  # "score" (adds risk points), "limit" (hard limit -> BLOCK) or "control" (policy control)
    summary: str


def _r(id, title, owasp, attack_class, kind, summary):
    return RuleInfo(id, title, tuple(owasp), attack_class, kind, summary)


CATALOG: Dict[str, RuleInfo] = {r.id: r for r in [
    _r("depth", "Query depth", ["API4"], "Deep nesting / circular relations", "score",
       "Nesting depth, counted through fragments. Cyclic relations let a short query fan out exponentially."),
    _r("breadth", "Selection breadth", ["API4"], "Wide selection", "score",
       "Fields selected after resolving fragments (schema-less mode; replaced by schema_cost when a schema is loaded)."),
    _r("duplicate_fields", "Duplicate selections", ["API4"], "Field duplication", "score",
       "The same response key selected repeatedly."),
    _r("complexity", "Heuristic complexity", ["API4"], "List amplification", "score",
       "Fields, arguments and list multipliers guessed from argument names (schema-less mode)."),
    _r("schema_cost", "Schema-aware cost", ["API4"], "List amplification / resource exhaustion", "score",
       "Static cost from the loaded schema: @cost weights and @listSize / slicing arguments, Apollo-compatible."),
    _r("subgraph_cost", "Per-subgraph cost", ["API4"], "Federation fan-out", "score",
       "Cost attributed to the subgraph that owns each field (supergraph schema); protects individual services."),
    _r("aliases", "Alias count", ["API4", "API2"], "Alias overloading", "score",
       "Many aliases batch lookups or login attempts into one request and defeat per-request rate limits."),
    _r("directives", "Directive count", ["API4"], "Directive overloading", "score",
       "Hundreds of @include/@skip directives on one operation."),
    _r("fragments", "Fragment definitions", ["API4"], "Fragment amplification", "score",
       "Many fragment definitions, the shape of fragment bombs."),
    _r("introspection", "Schema introspection", ["API8", "API9"], "Introspection abuse", "score",
       "__schema / __type reconnaissance; points grow with the size of the schema walk."),
    _r("unknown_fields", "Unknown fields", ["API8", "API9"], "Field suggestion probing", "score",
       "Fields that do not exist in the schema: typo-probing used to harvest 'Did you mean' suggestions."),
    _r("sensitive_fields", "Sensitive field names", ["API3", "API1"], "Sensitive data enumeration", "score",
       "Fields named like credentials or personal data, especially across many aliased lookups."),
    _r("mutation", "State-changing operation", ["API6"], "Sensitive business flow", "score",
       "Mutations are riskier than reads; small baseline."),
    _r("mutation_sensitive", "Mutation of sensitive fields", ["API2", "API3"], "Credential / PII mutation", "score",
       "A mutation touching credential-like fields."),
    _r("auth_bruteforce", "Credential guessing in one request", ["API2", "API6"], "Brute force via aliases / batching",
       "score", "The same credential-taking field (login, verify) repeated many times in one request."),
    _r("batching", "Batched operations", ["API4", "API2", "API6"], "Batching attack", "score",
       "A JSON array carrying many operations, evaluated as one combined workload."),
    _r("multi_vector", "Several abuse signals", ["API4"], "Combined abuse", "score",
       "Three or more independent signals in one operation."),
    _r("repeat_flood", "Repeated operation", ["API4", "API6"], "Automated flooding", "score",
       "The same client keeps sending the same operation at a high rate (behavioural)."),
    _r("ml_model", "Trained classifier", ["API4"], "Learned abuse patterns", "score",
       "Optional learned second opinion blended with the rule score; never the sole decision-maker."),
    _r("hard_limit", "Hard limit exceeded", ["API4"], "Resource exhaustion", "limit",
       "One or more deterministic limits was exceeded; always BLOCK."),
    _r("limit:query_length", "Query length limit", ["API4"], "Oversized request", "limit", "Query text too long."),
    _r("limit:max_depth", "Depth limit", ["API4"], "Deep nesting / circular relations", "limit",
       "Depth above max_depth."),
    _r("limit:alias_count", "Alias limit", ["API4", "API2"], "Alias overloading", "limit",
       "Aliases above max_aliases."),
    _r("limit:complexity", "Heuristic cost limit", ["API4"], "List amplification", "limit",
       "Heuristic cost above max_complexity."),
    _r("limit:schema_cost", "Schema cost limit", ["API4"], "List amplification / resource exhaustion", "limit",
       "Schema-aware cost above max_schema_cost."),
    _r("limit:subgraph_cost", "Subgraph cost limit", ["API4"], "Federation fan-out", "limit",
       "Cost on one subgraph above max_subgraph_cost."),
    _r("limit:token_count", "Token limit", ["API4"], "Oversized request", "limit", "Lexer tokens above max_tokens."),
    _r("limit:parse_budget_exceeded", "Parser budget", ["API4"], "Parser exhaustion", "limit",
       "Parsing exceeded the token or recursion budget."),
    _r("limit:introspection_disabled", "Introspection disabled", ["API8", "API9"], "Introspection abuse", "limit",
       "Introspection blocked by policy."),
    _r("limit:fragment_cycle", "Fragment cycle", ["API4"], "Circular fragments", "limit",
       "Fragments spread each other in a cycle."),
    _r("limit:unknown_fragment", "Unknown fragment", ["API4"], "Malformed document", "limit",
       "Spread of an undefined fragment."),
    _r("limit:batch_size", "Batch size limit", ["API4", "API2"], "Batching attack", "limit",
       "More operations than max_batch_size."),
    _r("limit:batching_disabled", "Batching disabled", ["API4", "API2"], "Batching attack", "limit",
       "Batching switched off by policy."),
    _r("limit:not_in_allowlist", "Not in persisted-operation allowlist", ["API9", "API8"], "Unregistered operation",
       "limit", "Enforced allowlist: only registered operations run."),
    _r("limit:subscriptions_disabled", "Subscriptions disabled", ["API4"], "Long-lived connection abuse", "limit",
       "Subscription operations blocked over HTTP."),
    _r("limit:subscription_count", "Subscription count", ["API4"], "Long-lived connection abuse", "limit",
       "More concurrent subscriptions on one WebSocket than max_subscriptions."),
    _r("control:mask_suggestions", "Field-suggestion masking", ["API8", "API9"], "Field suggestion probing", "control",
       "'Did you mean ...' hints are removed from upstream errors so schema names cannot be harvested."),
    _r("control:rate_limit", "Per-client rate limit", ["API4", "API2"], "Request flooding", "control",
       "Sliding-window request limit per client, returned as 429 with Retry-After."),
    _r("control:risky_quota", "High-risk quota", ["API4"], "Request flooding", "control",
       "THROTTLE tier: a small per-client quota of high-risk operations."),
]}


def annotate(explanation: dict) -> dict:
    """Attach ``owasp`` and ``attack_class`` to an explanation dict (in place) and return it."""
    entry = CATALOG.get(explanation.get("rule", ""))
    if entry:
        explanation["owasp"] = list(entry.owasp)
        explanation["attack_class"] = entry.attack_class
    return explanation


def limit_id(violation: str) -> str:
    """'max_depth>15' -> 'limit:max_depth'."""
    return "limit:" + re.split(r"[<>]", violation)[0]
