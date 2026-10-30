# Building and Evaluating an Explainable Security Gateway for GraphQL

*Draft for review. Not published. Every number comes from `ml/reports/evaluation.md` (seed 42); regenerate with
`python -m ml.run` before quoting anything.*

## 1. The problem

GraphQL lets a client decide the shape of its own request. One syntactically valid operation can nest a cyclic
relation fifty levels deep, alias a login mutation two hundred times, or hide that depth behind fragments. Request-level
tools (WAFs, per-IP rate limits) see one small POST. Classic mitigations - depth limits, cost limits, disabling
introspection - are effective but blunt: a single threshold has to separate a 14-widget dashboard from an alias-batching
attack.

This project builds **GraphQL Sentinel**, a gateway that analyses each operation, decides ALLOW / THROTTLE / BLOCK,
forwards allowed operations to the upstream, and records why. The goals were an honest engineering artefact and an
honest evaluation, not a claim of complete protection.

## 2. Design

*Threat model.* Operation-level abuse by unauthenticated or low-privilege clients (nesting, fragment amplification,
alias and field batching, list amplification, directive overload, introspection, sensitive-field enumeration).
Out of scope: authorisation flaws, resolver injection, anything not visible in the operation text.

*Pipeline.* Body limits → per-IP rate limit → parse under a token budget → fragment-aware feature extraction →
hard limits → rule score + ML probability → policy → enforcement → forwarding → audit event.

*Analysis.* Features are computed on the operation the server will execute, with fragment spreads resolved and
memoised per fragment. Two details mattered more than expected: depth hidden behind fragment chains must be counted,
and a "fragment bomb" (each fragment spreading the next several times) has an astronomical expanded size that can only
be reported, never enumerated. The analyzer analyses such documents in microseconds by treating sizes as saturating
counts, and detects fragment cycles instead of following them. Pathological nesting that exceeds the parser's recursion
budget becomes a BLOCK rather than a 500.

*Scoring.* A rule engine adds attributable points (depth, aliases, breadth, duplicates, cost with list multipliers,
sensitive fields, mutation + sensitive fields, fragments, directives, introspection, multi-vector bonus). The rule score is
the sum, so each explanation is exact. A scikit-learn classifier over the same 16 features produces a probability.
They are blended, `(1-w)·rules + w·100·p`, except that a very high rule score is never diluted. Hard limits are a separate
layer that can only raise severity.

*Safety properties that are tested, not assumed.* BLOCK never reaches the upstream; no upstream means 503, never a fake
success; upstream errors never leak hostnames or bodies; client identity for throttling is the IP, not a spoofable header;
all stores are bounded; credentials in query literals are redacted before persistence and variables are never stored; the
model file is checksum- and schema-verified before it is loaded.

## 3. Evaluation

*Data.* There is no public labelled corpus of GraphQL abuse, so I generated one: 23 categories (12 benign, 11 abusive)
by random walks over a fictional schema, with overlapping parameter ranges, de-duplicated by query skeleton and split
60/20/20 per category. A second dataset from another seed serves as a confirmation set, and 208 real benign queries from
the NL2GQL test set measure false positives. Labels reflect generator intent.

*Baselines.* Hard limits only; a single depth/cost threshold tuned on validation; rules only; ML only; the shipped blend.

*Results (held-out test, flagged = MEDIUM risk or above or a limit violation).* Limits-only: F1 0.51 (recall 0.39).
Tuned threshold: F1 0.67 but 77% false positives. Rules: F1 0.77. ML alone: F1 ≈ 1.00. Blend: F1 0.88 (precision 0.79,
recall 0.99, FPR 0.24). On the real benign queries the blend flags 3.4%.

*The interesting result is the one that argues against the best-looking number.* The classifier's near-perfect score is a
property of the generator: with a whole abusive category withheld from training, its recall is 0.00 for field duplication and
wide selections, 0.19 for introspection and 0.53 for deep nesting, while rules retain 0.74-1.00. In-distribution validation
would have chosen "ML only"; selecting model and blend weight by *leave-one-attack-category-out* F1 on the validation split
chose a blend (weight 0.4) in which rules keep the final say on very high scores.

*Threats to validity (all in the report).* Synthetic data from one schema and one author; labels from generator intent;
the benign class includes deliberately heavy negatives so 24% FPR there is a stress figure; generator ranges, rule
thresholds and the default cost limit were revised twice after looking at aggregate results of earlier runs, which the
independent confirmation set cannot undo; latency numbers come from one machine with a stub upstream; behavioural features
and rate limiting are not evaluated offline.

## 4. Lessons learned

1. A perfect in-distribution score on synthetic data is a warning, not a result. Evaluate on withheld *categories*.
2. Make the explanation the computation (additive attributed points) rather than a post-hoc approximation.
3. Hard limits and risk scores answer different questions; keep them separate so a model can never loosen a limit.
4. Most of the engineering effort went into boring guarantees (no fake success, bounded memory, redaction,
   spoof-resistant identity) and into tests that pin them down.
5. Per-call thread-pool control in scikit-learn cost ~50 ms per prediction; measuring end-to-end latency found it.

## 5. Limitations and future work

Not a WAF; unauthenticated dashboard API; per-process limiter state; no persisted queries, subscriptions or batched
requests. Next: evaluation on real labelled traffic, shared rate-limit state, authenticated dashboard API, and a
public dataset release (not done; would need review).

## Reproducibility

`pip install -r ml/requirements.txt && python -m ml.run --seed 42` regenerates the dataset, model and all numbers.
Code and documentation: <https://github.com/satyamshrivastav955-dotcom/GraphQL-Sentinel>.
