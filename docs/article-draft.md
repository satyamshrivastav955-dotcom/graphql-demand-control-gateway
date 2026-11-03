# Building an Explainable Demand-Control Gateway for GraphQL APIs

**Subtitle:** *AST analysis, query-cost enforcement, hybrid risk scoring, and reproducible security evaluation.*

*Draft technical article for review. Not published.*

---

### Article Metadata

- **Suggested Publication Platforms:** Dev.to, Hashnode, Medium (Engineering/AppSec)
- **Primary Keywords:** `graphql`, `application-security`, `python`, `fastapi`, `machine-learning`, `api-gateway`, `cybersecurity`
- **Canonical Repository:** [https://github.com/satyamshrivastav955-dotcom/graphql-demand-control-gateway](https://github.com/satyamshrivastav955-dotcom/graphql-demand-control-gateway)
- **Author:** Satyam Santosh Shrivastav ([GitHub](https://github.com/satyamshrivastav955-dotcom))

---

### Abstract

GraphQL empowers client applications by allowing them to define the exact shape and nested depth of the data they request over a single HTTP endpoint. However, this flexibility fundamentally shifts computational burden from client to server, introducing distinct resource-exhaustion vectors—such as recursive fragment spreads, combinatorial alias batching, and unbounded cyclic nesting—that traditional HTTP-layer Web Application Firewalls (WAFs) and IP rate limiters fail to detect. 

This paper documents the design, implementation, and empirical evaluation of **GraphQL Demand Control Gateway**, an explainable, self-hosted reverse-proxy gateway built with FastAPI, `graphql-core`, and scikit-learn. The gateway intercepts inbound GraphQL operations, parses their Abstract Syntax Tree (AST) under strict resource budgets, calculates deterministic complexity metrics, and blends an explainable additive rule score with a calibrated machine-learning risk estimate to enforce `ALLOW`, `THROTTLE`, or `BLOCK` decisions before requests touch upstream execution engines. We evaluate five detection approaches across a reproducible 23-category dataset and demonstrate that while a standalone ML classifier achieves near-perfect in-distribution metrics ($F_1 = 0.998$), it fails completely ($0.00$ recall) on unseen structural attack vectors under leave-one-attack-category-out (LOCO) testing. We explain why an explainable, rule-backed hybrid design is necessary for robust operational defence and report end-to-end latency benchmarks and production deployment architecture.

---

## 1. Introduction: The Asymmetry of GraphQL Operations

In traditional REST architectures, backend engineers expose a fixed hierarchy of parameterized endpoints (e.g., `GET /api/v1/users/{id}`). The resource consumption of each endpoint is bounded and predictable. Network firewalls, API gateways, and cloud WAFs inspect the HTTP method, URI path, and query parameters to enforce coarse-grained rate limits per IP address.

GraphQL breaks this operational model. A GraphQL service exposes a single endpoint—typically `POST /graphql`—that accepts arbitrary operation text within the request payload. Under standard HTTP inspection, two operations of identical payload size can produce radically different backend workloads:

1. **A benign dashboard query:** A 400-byte payload requesting 5 scalar fields on a single user profile executes in 3 milliseconds across one database query.
2. **A fragment amplification attack:** A 434-byte document defining eight mutually referencing fragment definitions that expands to **16,403 field executions**, inducing resolver exhaustion, database thread pool starvation, and service degradation.

To an upstream reverse proxy or perimeter WAF, both requests appear as identical `POST` transactions with identical headers and similar content lengths. Traditional per-IP rate limiters cannot differentiate between an aggressive automated scanner and a legitimate browser dashboard running complex queries.

Securing a GraphQL service requires **operation-aware analysis**: the gateway must parse the document, inspect the AST, expand fragment spreads, compute execution complexity, and evaluate security policies *before* forwarding the operation to the upstream resolver.

```
Ordinary HTTP Proxy:
Client Request ───► [ HTTP Method + URL Path Inspection ] ───► Upstream Server
                             │
                             ▼ (Blind to internal query payload complexity)

GraphQL Demand Control Gateway:
Client Request ───► [ Token Budget & Lexical Limits ]
                          │
                          ▼
                    [ AST Parsing & Memoized Fragment Expansion ]
                          │
                          ▼
                    [ 16 Extracted Structural & Cost Features ]
                          │
                          ▼
                    [ Rule Engine + Calibrated Risk Model ]
                          │
                          ├──► ALLOW    ───► Upstream GraphQL Server
                          ├──► THROTTLE ───► HTTP 429 (Per-Client Token Bucket)
                          └──► BLOCK    ───► HTTP 403 (Zero Upstream Traffic)
```

This project designs and implements an open-source, explainable demand-control gateway. It is not presented as a silver bullet or an autonomous AI security replacement. Rather, it represents an engineering reference implementation demonstrating how deterministic AST analysis, strict parsing budgets, and transparent scoring can protect GraphQL backends against operation-level abuse.

---

## 2. Problem Space & Threat Model

### In-Scope Vulnerabilities (Operation-Level Abuse)

The gateway addresses threats that manifest directly within the operation syntax:

1. **Deep Nesting:** Traversing cyclic schema relations (e.g., `user -> friends -> friends -> ...`) to force dozens of nested database joins.
2. **Fragment Amplification ("Fragment Bombs"):** Defining chains of fragments where each fragment spreads the subsequent one multiple times. Without memoized expansion, the parser or validator triggers combinatorial CPU spikes ($\mathcal{O}(k^d)$).
3. **Alias Batching & Enumeration:** Utilizing GraphQL field aliasing (`a1: user(id: 1), a2: user(id: 2), ...`) to bypass HTTP rate limits and execute hundreds of discrete operations in a single HTTP request.
4. **Field Duplication:** Requesting the same expensive field dozens of times under distinct aliases to multiply server computation.
5. **List Amplification:** Supplying massive values to pagination arguments (e.g., `first: 10000`, `limit: 50000`) that trigger out-of-memory errors in database drivers.
6. **Directive Overload:** Stacking dozens of `@include` or `@skip` directives across execution nodes to exhaust traversal stacks.
7. **Aggressive Introspection:** Scraping schema internals (`__schema`, `__type`) during production reconnaissance to map hidden entities.
8. **Sensitive Field Enumeration:** Targeting sensitive fields (e.g., `ssn`, `password_hash`, `stripe_id`) across broad collections.

### Out-of-Scope Vulnerabilities

This gateway does **not** protect against flaws that are invisible in the operation text:
- **Broken Object-Level Authorization (BOLA / IDOR):** If a user is authorized to call `user(id: $id)` but queries an unauthorized ID, enforcement belongs inside the application's resolver layer.
- **SQL / NoSQL Injection in Resolvers:** If an application improperly interpolates GraphQL arguments into raw SQL queries, parameterization must occur at the data layer.
- **Business Logic Flaws:** Subtle logic flaws in domain resolvers cannot be determined from query structure alone.

---

## 3. System Architecture

The gateway is built in Python 3.12+ using FastAPI, `graphql-core` (the Python implementation of the reference GraphQL specification), and `scikit-learn`.

```
                         ┌────────────────────────────────────────────────────────┐
                         │              Client Application / Attacker            │
                         └───────────────────────────┬────────────────────────────┘
                                                     │ HTTP POST /graphql-proxy
                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FastAPI Gateway Runtime (backend/api/gateway.py)                                                │
│                                                                                                 │
│  1. Request Validation: JSON object check, single operation constraint, 64 KB body size limit   │
│  2. Lexical Hard Limits: Query string length check, token count budget (2,000 tokens)           │
│  3. AST Analysis (backend/core/analysis/analyzer.py):                                           │
│     - graphql-core Parser (parse budget: max recursion depth 100)                              │
│     - Memoized Fragment Graph Traversal & Cycle Detection                                       │
│     - Saturating Field Counters (prevents integer/memory blowout on fragment bombs)             │
│  4. Feature Extraction: Extracts 16 numerical signals (depth, aliases, directives, cost...)     │
│  5. Hybrid Scoring Engine (backend/core/security_engine/scorer.py):                             │
│     - Attributable Rule Engine: Deterministic additive points (0 - 100)                         │
│     - Histogram Gradient Boosting Classifier: Probabilistic score ($p \in [0, 1]$)             │
│     - Calibrated Score Blend: $(1 - w) \cdot \text{rules} + w \cdot 100 \cdot p$ (weight $w=0.4$)│
│  6. Policy Enforcement (backend/core/security_engine/policy.py):                                │
│     - Hard Limits Check: Depth > 15, Cost > 500, Aliases > 30 (Forces CRITICAL/BLOCK)           │
│     - Tier Assignment: SAFE (0-24) | LOW (25-49) | MEDIUM (50-74) | HIGH (75-89) | CRITICAL (90+)│
│     - Mode Selection: Enforce Mode (Standard) vs Shadow Mode (Report-only)                      │
│  7. Action Handler:                                                                             │
│     - ALLOW: Proxies request to upstream with connection pooling via httpx.AsyncClient          │
│     - THROTTLE: Checks sliding-window token bucket (5 req/min per client IP). Returns 429.      │
│     - BLOCK: Immediately aborts request. Returns 403 Forbidden with security extensions.        │
│  8. Audit & Observability (backend/core/runtime/):                                              │
│     - Event Store: Writes full decision metadata, rules, and redacted query to SQLite           │
│     - Metrics Collector: Increments Prometheus counters (requests, latency, limit violations)  │
│     - Alert Dispatcher: Asynchronously notifies Slack/Discord webhook on blocked operations     │
└────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                             │ [ALLOW only]
                                             ▼
                         ┌────────────────────────────────────────────────────────┐
                         │              Upstream GraphQL Engine / API             │
                         └────────────────────────────────────────────────────────┘
```

### Component Breakdown

1. **`backend/core/analysis/analyzer.py`**: Intercepts the raw GraphQL document, calculates depth, resolves inline and named fragments, detects circular fragment dependencies, and evaluates an estimated execution cost with list-size multiplication.
2. **`backend/core/security_engine/rules.py`**: Implements 11 transparent, rule-based checks that map AST metrics directly to risk points. Every rule violation generates a human-readable explanation with exact line numbers.
3. **`backend/core/models/risk_model.joblib`**: A compact Histogram Gradient Boosting classifier trained on synthetic GraphQL operations. It is validated with a SHA-256 checksum and strict feature schema verification before runtime loading.
4. **`backend/core/runtime/limiter.py`**: Implements in-memory sliding-window token bucket rate limiters per client IP for ordinary traffic and high-risk throttled queries.
5. **`backend/core/runtime/events.py`**: An SQLite-backed append-only audit repository. It redacts literal values (passwords, tokens, emails) from queries before persistence and automatically prunes historical records beyond configured retention boundaries.
6. **`dashboard/`**: A React 19 + TypeScript + Vite console. It provides a real-time event inspector, an interactive query analysis playground, policy configuration inspection, and an offline benchmark visualizer.

---

## 4. Implementation Details & Defensive Engineering

### A. Memoized Fragment Expansion and Saturating Counters

A recurring vulnerability in naive GraphQL analyzers is susceptibility to **fragment bombs**. Consider this minimal payload:

```graphql
query Bomb { ...F1 }
fragment F1 on Query { ...F2 ...F2 }
fragment F2 on Query { ...F3 ...F3 }
fragment F3 on Query { ...F4 ...F4 }
# ... cascading to F8
```

If an analyzer recursively traverses fragment spreads without memoization, an 8-fragment document causes $2^8 = 256$ traversals; 20 fragments cause over 1,000,000 operations, freezing the gateway.

In `backend/core/analysis/analyzer.py`, we implement two defensive techniques:
1. **Memoization by Fragment Name:** Each fragment's expanded metrics (depth, scalar count, field count, aliases) are calculated exactly once. When encountered elsewhere in the AST, the cached metrics are merged in $\mathcal{O}(1)$ time.
2. **Saturating Counters:** If fragment multiplication exceeds safety thresholds ($100,000$ fields), counts are saturated rather than allowing integer overflow or unbounded memory allocations.
3. **Active Cycle Detection:** A recursion tracking set detects cyclic references (`FragmentA -> FragmentB -> FragmentA`) and halts expansion immediately, flagging a `fragment_cycle` limit violation.

```python
# excerpt from backend/core/analysis/analyzer.py
def _resolve_fragment(self, name: str, visited: set) -> FragmentMetrics:
    if name in visited:
        self.violations.append("fragment_cycle_detected")
        return FragmentMetrics.empty()
    if name in self._fragment_cache:
        return self._fragment_cache[name]

    visited.add(name)
    metrics = self._analyze_selection_set(self.fragments[name].selection_set, visited)
    visited.remove(name)
    
    self._fragment_cache[name] = metrics
    return metrics
```

### B. Additive Explainability vs. Black-Box Scoring

Security gateways cannot act as opaque black boxes. When a legitimate client query is rejected with HTTP 403, developers require actionable diagnostics.

In our architecture, the **Rule Engine** computes an explicit additive score:
$$\text{Score}_{\text{rules}} = \min\left(100, \sum_{i} \text{Points}(R_i)\right)$$

Each activated rule returns an explanation dictionary containing the rule ID, human-readable description, numerical weight, and exact AST trigger line:

```json
{
  "rule": "RULE_ALIAS_BATCHING",
  "points": 35.0,
  "description": "High alias count (24 aliases detected)",
  "evidence": {"alias_count": 24, "threshold": 10}
}
```

The ML model outputs a probabilistic risk estimate $p \in [0.0, 1.0]$. The production score is a calibrated blend:
$$\text{Score}_{\text{final}} = (1 - w) \cdot \text{Score}_{\text{rules}} + w \cdot (100 \cdot p)$$

Where $w = 0.40$, selected via leave-one-category-out cross-validation. Furthermore, we enforce an invariant: **an ML model score can never dilute a severe rule score**. If $\text{Score}_{\text{rules}} \ge 85.0$, the rule score takes precedence, preventing a misclassified low-probability ML inference from overturning an explicit rule violation.

### C. True THROTTLE Enforcement

Many commercial gateways define "throttling" as artificially delaying the HTTP response (`sleep(delay)`). This approach is hazardous: holding client connections open exhausts reverse-proxy worker threads and file descriptors.

Our gateway implements true rate-based throttling:
- Queries categorized in the `SAFE` or `LOW` tiers are forwarded immediately.
- Queries assigned to the `THROTTLE` tier (score 50–74) are subject to a strict per-client sliding-window quota (default: 5 requests per 60-second window).
- When a client exhausts their throttle quota, the gateway immediately returns **HTTP 429 Too Many Requests** with a standard `Retry-After: 60` header, dropping the request without consuming upstream compute or holding connection sockets open.

---

## 5. Experimental Methodology

### Synthetic Dataset Construction

Publicly available, labeled datasets of malicious GraphQL traffic do not exist in the cybersecurity research community. To train and evaluate the scoring engine, we engineered a deterministic synthetic generator (`ml/dataset/generator.py`).

The generator performs seeded random walks over a realistic, multi-entity e-commerce/social schema (Users, Orders, Products, Reviews, Payments) with cyclic relationships:
- **23 Structured Categories:** 12 benign operational categories (lookups, paginated views, nested profiles, dashboards, variable-driven queries) and 11 abusive categories (deep nesting, alias batching, fragment bombs, list amplification, directive stuffing, introspection).
- **Overlapping Parameter Ranges:** To test realistic edge cases, parameter boundaries intentionally overlap. For example, benign dashboards query up to 14 fields/aliases, while malicious alias batching begins at 6 aliases.
- **Query Skeleton De-Duplication:** All queries are normalized into *skeletons* (stripping variable literals, comments, and whitespace). No two identical skeletons exist across splits.
- **Split Distribution:** 60% Train (12,866 queries), 20% Validation (4,285 queries), and 20% Held-Out Test (4,298 queries).
- **Independent Confirmation Set:** A second dataset generated with a distinct seed, filtered to remove any skeletons present in the primary training set.

### Evaluation Metric Definition

An operation is considered **flagged** by a method if its assigned score places it in the `MEDIUM` tier or higher ($\text{Score} \ge 50.0$), or if it triggers an immediate hard limit violation.

---

## 6. Experimental Results & The Generalization Trap

We evaluated five distinct detection strategies against the held-out test split (4,298 operations, 47.4% attack ratio):

| Detection Method | Precision | Recall | $F_1$ Score | False Positive Rate (FPR) |
|---|---:|---:|---:|---:|
| **Hard limits only** (Depth > 15, Cost > 500, Aliases > 30) | 0.758 | 0.388 | 0.514 | 0.112 |
| **Tuned Depth/Cost threshold** (Depth $\ge 3$, Cost $\ge 25$) | 0.524 | 0.945 | 0.674 | 0.773 |
| **Rule Engine alone** (Additive attributable rules) | 0.680 | 0.898 | 0.774 | 0.381 |
| **ML Classifier alone** (Histogram Gradient Boosting, $p \ge 0.5$) | **0.998** | **0.999** | **0.998** | **0.002** |
| **Combined Production Scorer** (Blend $w=0.4$ + Hard Limits) | **0.791** | **0.994** | **0.881** | **0.237** |

```
Precision vs. Recall Comparison Across Methods:

Hard Limits Only:     [████████████░░░░] Rec: 0.388 | Prec: 0.758
Tuned Threshold:      [████████████████] Rec: 0.945 | Prec: 0.524 (FPR: 77.3%!)
Rule Engine Alone:    [███████████████░] Rec: 0.898 | Prec: 0.680
ML Classifier Alone:  [████████████████] Rec: 0.999 | Prec: 0.998 (In-distribution)
Combined Production:  [████████████████] Rec: 0.994 | Prec: 0.791 (FPR: 23.7%)
```

### The Machine Learning Generalization Trap

At first glance, the standalone ML classifier appears nearly flawless ($F_1 = 0.998$, False Positive Rate = $0.2\%$). In a traditional data science workflow, an engineer would ship the ML model alone and discard the deterministic rules.

However, synthetic training splits share subtle structural distributions with the generator. To evaluate how the model handles **novel, zero-day attack variations**, we conducted **Leave-One-Attack-Category-Out (LOCO)** cross-validation. In each fold, an entire attack category was completely removed from the training set, and the model was evaluated on its ability to detect the withheld attack:

| Withheld Attack Category | ML Classifier Recall | Rule Engine Recall | Combined Engine Recall |
|---|---:|---:|---:|
| **Field Duplication** | **0.000** | 0.740 | **0.740** |
| **Wide Selection** | **0.000** | 0.990 | **0.990** |
| **Introspection Scraping** | **0.190** | 1.000 | **1.000** |
| **Deep Nesting** | **0.525** | 1.000 | **1.000** |
| **Directive Overload** | 0.885 | 0.865 | 0.995 |

When field duplication or wide selections were excluded from training, the machine learning classifier's detection rate collapsed to **0.0%**. Because the model had never observed those specific feature combinations, it classified massive malicious queries as completely benign.

In contrast, the deterministic Rule Engine maintained consistent detection ($74\% - 100\%$) because its thresholds reflect fundamental physical constraints rather than statistical correlation.

**Key Finding:** Machine learning models trained on synthetic security data overfit to generator artifacts. Production gateways must utilize ML to augment and fine-tune scores on ambiguous queries, but **must never abandon deterministic heuristic rules or independent hard limits**.

---

## 7. Performance Benchmarks

To establish local baseline latency and throughput, we executed automated load tests using `scripts/loadtest.py`.

### Benchmark Environment
- **Host OS:** Windows 11 Enterprise (x64)
- **CPU:** Intel Core i7 / 16 Logical Cores
- **Runtime:** Python 3.13.13 (single-process Uvicorn worker)
- **Database:** Local SQLite with WAL mode (`sentinel.db`)
- **Topology:** Gateway, demo upstream, and load generator running concurrently on the local loopback interface (`127.0.0.1`).

### Empirical Latency & Concurrency Results

| Concurrency | Throughput (req/s) | Median Latency (p50) | 95th Percentile (p95) | 99th Percentile (p99) | Error Rate |
|---|---|---|---|---|---|
| **1 Worker** | 77.4 req/s | 11.2 ms | 23.4 ms | 31.8 ms | 0.0% |
| **4 Workers** | 177.2 req/s | 20.1 ms | 41.8 ms | 56.2 ms | 0.0% |
| **32 Workers** | 162.8 req/s | 171.4 ms | 412.0 ms | 520.1 ms | 0.0% |

At moderate concurrency ($c=4$), the gateway sustains approximately 180 requests per second with a median latency of 20 milliseconds, including complete AST parsing, feature extraction, ML inference, and disk-persisted SQLite event auditing. Under extreme saturation ($c=32$), queuing latency increases, demonstrating that production high-throughput deployments should deploy multiple Uvicorn worker processes behind an Nginx or Caddy reverse proxy.

---

## 8. Limitations & Production Readiness

In accordance with responsible engineering practices, we explicitly document the current architectural limitations:

1. **Process-Local Rate Limiting:** Sliding-window token buckets and IP counters reside in process memory. Running multiple container replicas without sticky routing currently divides limits. Production horizontal scaling requires a Redis-backed rate-limiting backend.
2. **Single Shared Management Token:** The management API uses a single operator token. Role-Based Access Control (RBAC) and OIDC integration remain future enhancements.
3. **Synthetic Evaluation Ground Truth:** Ground-truth labels reflect synthetic generator intent. Real-world production traffic contains domain-specific legitimate queries (e.g., massive internal reporting queries) that may require custom allow-listing.
4. **Third-Party Data Provenance Notice:** As disclosed in `NOTICE.md`, 208 queries from the `NL2GQL` benchmark were evaluated to measure benign false-positive rates ($3.4\%$). The exact file licensing provenance remains unverified; consequently, these queries are excluded from core repository distribution grants.
5. **Not an Authorization Gateway:** The gateway protects service availability; it does not replace fine-grained object-level authorization (BOLA) within application resolvers.

---

## 9. Conclusion & Future Roadmap

The GraphQL Demand Control Gateway demonstrates that operation-level security does not require opaque, non-deterministic black-box models. By combining memoized AST parsing, explainable additive scoring, and calibrated machine learning, the gateway effectively defuses structural attacks before they reach backend resolvers.

### Roadmap for v1.1
- **Redis-Backed Distributed State:** Shared token buckets across multi-node Kubernetes deployments.
- **Schema-Aware `@cost` Directives:** Ingesting GraphQL SDL schemas to apply custom cost weights directly to database-intensive resolvers.
- **Persisted Query Allow-Listing:** Automatic hashing and pre-authorization of approved client documents.

---

## References

1. **GraphQL Foundation.** (2024). *GraphQL Security Best Practices.* [https://graphql.org/learn/security/](https://graphql.org/learn/security/)
2. **OWASP Foundation.** (2025). *OWASP GraphQL Cheat Sheet.* OWASP Cheat Sheet Series. [https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)
3. **GraphQL Specification.** (2021). *GraphQL: A query language for APIs.* Working Draft. [https://spec.graphql.org/](https://spec.graphql.org/)
4. **Pedregosa, F., et al.** (2011). *Scikit-learn: Machine Learning in Python.* Journal of Machine Learning Research, 12, 2825-2830.
5. **Fielding, R., et al.** (2022). *HTTP Semantics (RFC 9110).* Internet Engineering Task Force (IETF). [https://www.rfc-editor.org/rfc/rfc9110.html](https://www.rfc-editor.org/rfc/rfc9110.html)

---

### Author Bio

**Satyam Santosh Shrivastav** is a computer science and engineering student focused on application security, distributed systems, and machine learning infrastructure.  
- GitHub: [github.com/satyamshrivastav955-dotcom](https://github.com/satyamshrivastav955-dotcom)  
- Project Repository: [graphql-demand-control-gateway](https://github.com/satyamshrivastav955-dotcom/graphql-demand-control-gateway)
