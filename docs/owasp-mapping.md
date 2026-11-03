# OWASP API Security Top 10 (2023) mapping

Generated from `sentinel_core/catalog.py` by `scripts/export_owasp_mapping.py`; a test fails if this file is stale.
Every explanation in an API response and in the audit log carries the `owasp` categories and `attack_class` below.

Sentinel inspects the GraphQL *operation*, so it addresses API4 (resource consumption), API8/API9 (reconnaissance and
unregistered operations) and the parts of API1-API3 and API6 that are visible in the request shape (enumeration
across aliases, credential guessing, sensitive-field harvesting). It does not do authorization (API1, API3, API5
proper), SSRF (API7) or outbound-call safety (API10); those stay in the application.

## By OWASP category

| Category | Name | Rules and controls |
|---|---|---|
| API1:2023 | Broken Object Level Authorization | `sensitive_fields` |
| API2:2023 | Broken Authentication | `aliases`, `mutation_sensitive`, `auth_bruteforce`, `batching`, `limit:alias_count`, `limit:batch_size`, `limit:batching_disabled`, `control:rate_limit` |
| API3:2023 | Broken Object Property Level Authorization | `sensitive_fields`, `mutation_sensitive` |
| API4:2023 | Unrestricted Resource Consumption | `depth`, `breadth`, `duplicate_fields`, `complexity`, `schema_cost`, `subgraph_cost`, `aliases`, `directives`, `fragments`, `batching`, `multi_vector`, `repeat_flood`, `ml_model`, `hard_limit`, `limit:query_length`, `limit:max_depth`, `limit:alias_count`, `limit:complexity`, `limit:schema_cost`, `limit:subgraph_cost`, `limit:token_count`, `limit:parse_budget_exceeded`, `limit:fragment_cycle`, `limit:unknown_fragment`, `limit:batch_size`, `limit:batching_disabled`, `limit:subscriptions_disabled`, `limit:subscription_count`, `control:rate_limit`, `control:risky_quota` |
| API5:2023 | Broken Function Level Authorization | not addressed (out of scope) |
| API6:2023 | Unrestricted Access to Sensitive Business Flows | `mutation`, `auth_bruteforce`, `batching`, `repeat_flood` |
| API7:2023 | Server Side Request Forgery | not addressed (out of scope) |
| API8:2023 | Security Misconfiguration | `introspection`, `unknown_fields`, `limit:introspection_disabled`, `limit:not_in_allowlist`, `control:mask_suggestions` |
| API9:2023 | Improper Inventory Management | `introspection`, `unknown_fields`, `limit:introspection_disabled`, `limit:not_in_allowlist`, `control:mask_suggestions` |
| API10:2023 | Unsafe Consumption of APIs | not addressed (out of scope) |

## By rule

| Rule | Kind | OWASP | GraphQL attack class | What it does |
|---|---|---|---|---|
| `depth` | score | API4 | Deep nesting / circular relations | Nesting depth, counted through fragments. Cyclic relations let a short query fan out exponentially. |
| `breadth` | score | API4 | Wide selection | Fields selected after resolving fragments (schema-less mode; replaced by schema_cost when a schema is loaded). |
| `duplicate_fields` | score | API4 | Field duplication | The same response key selected repeatedly. |
| `complexity` | score | API4 | List amplification | Fields, arguments and list multipliers guessed from argument names (schema-less mode). |
| `schema_cost` | score | API4 | List amplification / resource exhaustion | Static cost from the loaded schema: @cost weights and @listSize / slicing arguments, Apollo-compatible. |
| `subgraph_cost` | score | API4 | Federation fan-out | Cost attributed to the subgraph that owns each field (supergraph schema); protects individual services. |
| `aliases` | score | API4, API2 | Alias overloading | Many aliases batch lookups or login attempts into one request and defeat per-request rate limits. |
| `directives` | score | API4 | Directive overloading | Hundreds of @include/@skip directives on one operation. |
| `fragments` | score | API4 | Fragment amplification | Many fragment definitions, the shape of fragment bombs. |
| `introspection` | score | API8, API9 | Introspection abuse | __schema / __type reconnaissance; points grow with the size of the schema walk. |
| `unknown_fields` | score | API8, API9 | Field suggestion probing | Fields that do not exist in the schema: typo-probing used to harvest 'Did you mean' suggestions. |
| `sensitive_fields` | score | API3, API1 | Sensitive data enumeration | Fields named like credentials or personal data, especially across many aliased lookups. |
| `mutation` | score | API6 | Sensitive business flow | Mutations are riskier than reads; small baseline. |
| `mutation_sensitive` | score | API2, API3 | Credential / PII mutation | A mutation touching credential-like fields. |
| `auth_bruteforce` | score | API2, API6 | Brute force via aliases / batching | The same credential-taking field (login, verify) repeated many times in one request. |
| `batching` | score | API4, API2, API6 | Batching attack | A JSON array carrying many operations, evaluated as one combined workload. |
| `multi_vector` | score | API4 | Combined abuse | Three or more independent signals in one operation. |
| `repeat_flood` | score | API4, API6 | Automated flooding | The same client keeps sending the same operation at a high rate (behavioural). |
| `ml_model` | score | API4 | Learned abuse patterns | Optional learned second opinion blended with the rule score; never the sole decision-maker. |
| `hard_limit` | limit | API4 | Resource exhaustion | One or more deterministic limits was exceeded; always BLOCK. |
| `limit:query_length` | limit | API4 | Oversized request | Query text too long. |
| `limit:max_depth` | limit | API4 | Deep nesting / circular relations | Depth above max_depth. |
| `limit:alias_count` | limit | API4, API2 | Alias overloading | Aliases above max_aliases. |
| `limit:complexity` | limit | API4 | List amplification | Heuristic cost above max_complexity. |
| `limit:schema_cost` | limit | API4 | List amplification / resource exhaustion | Schema-aware cost above max_schema_cost. |
| `limit:subgraph_cost` | limit | API4 | Federation fan-out | Cost on one subgraph above max_subgraph_cost. |
| `limit:token_count` | limit | API4 | Oversized request | Lexer tokens above max_tokens. |
| `limit:parse_budget_exceeded` | limit | API4 | Parser exhaustion | Parsing exceeded the token or recursion budget. |
| `limit:introspection_disabled` | limit | API8, API9 | Introspection abuse | Introspection blocked by policy. |
| `limit:fragment_cycle` | limit | API4 | Circular fragments | Fragments spread each other in a cycle. |
| `limit:unknown_fragment` | limit | API4 | Malformed document | Spread of an undefined fragment. |
| `limit:batch_size` | limit | API4, API2 | Batching attack | More operations than max_batch_size. |
| `limit:batching_disabled` | limit | API4, API2 | Batching attack | Batching switched off by policy. |
| `limit:not_in_allowlist` | limit | API9, API8 | Unregistered operation | Enforced allowlist: only registered operations run. |
| `limit:subscriptions_disabled` | limit | API4 | Long-lived connection abuse | Subscription operations blocked over HTTP. |
| `limit:subscription_count` | limit | API4 | Long-lived connection abuse | More concurrent subscriptions on one WebSocket than max_subscriptions. |
| `control:mask_suggestions` | control | API8, API9 | Field suggestion probing | 'Did you mean ...' hints are removed from upstream errors so schema names cannot be harvested. |
| `control:rate_limit` | control | API4, API2 | Request flooding | Sliding-window request limit per client, returned as 429 with Retry-After. |
| `control:risky_quota` | control | API4 | Request flooding | THROTTLE tier: a small per-client quota of high-risk operations. |
