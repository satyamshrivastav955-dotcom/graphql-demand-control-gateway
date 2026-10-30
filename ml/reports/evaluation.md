# Evaluation results

Generated 2026-10-29T20:58:46Z | seed 42 | dataset v1.0 (train 12866, val 4285, test 4298; 47% abusive in test)

## Detection on the held-out test split
Flagged = at least MEDIUM_RISK or a hard-limit violation. `Enf. recall/FPR` use decision != ALLOW.

| Method | Precision | Recall | F1 | FPR | ROC-AUC | PR-AUC | Enf. recall | Enf. FPR | p50 us | p95 us |
|---|---|---|---|---|---|---|---|---|---|---|
| Hard limits only | 0.758 | 0.388 | 0.514 | 0.112 | - | - | 0.388 | 0.112 | 4677 | 34228 |
| Depth/cost threshold | 0.524 | 0.945 | 0.674 | 0.773 | - | - | 0.945 | 0.773 | 4677 | 34228 |
| Rule scorer | 0.680 | 0.898 | 0.774 | 0.381 | 0.817 | 0.731 | 0.762 | 0.240 | 4754 | 34326 |
| ML classifier | 0.998 | 0.999 | 0.998 | 0.002 | 1.000 | 1.000 | 0.999 | 0.002 | 17914 | 47736 |
| Combined (production) | 0.791 | 0.994 | 0.881 | 0.237 | 0.872 | 0.767 | 0.890 | 0.188 | 18012 | 47834 |

## Share flagged by category (test split)

| Category | n | Hard limits only | Depth/cost threshold | Rule scorer | ML classifier | Combined (production) |
|---|---|---|---|---|---|---|
| alias_batching | 200 | 0.41 | 0.99 | 0.84 | 1.00 | 1.00 |
| conditional_fields (benign) | 200 | 0.00 | 0.96 | 0.01 | 0.00 | 0.00 |
| credential_stuffing | 144 | 0.30 | 0.85 | 1.00 | 1.00 | 1.00 |
| dashboard (benign) | 200 | 0.01 | 1.00 | 0.62 | 0.00 | 0.42 |
| deep_nesting | 200 | 0.52 | 1.00 | 0.81 | 1.00 | 1.00 |
| directive_overload | 200 | 0.10 | 0.89 | 0.75 | 1.00 | 0.96 |
| field_duplication | 199 | 0.00 | 0.95 | 0.74 | 1.00 | 1.00 |
| fragment_bomb | 200 | 0.66 | 1.00 | 1.00 | 1.00 | 1.00 |
| fragment_depth | 200 | 0.66 | 1.00 | 1.00 | 1.00 | 1.00 |
| fragment_reuse (benign) | 200 | 0.00 | 0.99 | 0.33 | 0.01 | 0.20 |
| full_profile (benign) | 143 | 0.00 | 0.76 | 0.35 | 0.00 | 0.31 |
| heavy_report (benign) | 200 | 0.81 | 1.00 | 0.98 | 0.01 | 0.96 |
| introspection | 164 | 0.00 | 0.74 | 1.00 | 1.00 | 1.00 |
| list_amplification | 200 | 0.71 | 1.00 | 0.84 | 0.99 | 0.97 |
| list_page (benign) | 200 | 0.14 | 1.00 | 0.38 | 0.00 | 0.17 |
| login (benign) | 151 | 0.00 | 0.00 | 0.87 | 0.00 | 0.00 |
| lookup (benign) | 199 | 0.00 | 0.47 | 0.02 | 0.00 | 0.00 |
| mutation (benign) | 168 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| nested_view (benign) | 200 | 0.20 | 1.00 | 0.61 | 0.01 | 0.49 |
| sensitive_enumeration | 200 | 0.14 | 0.93 | 0.98 | 1.00 | 1.00 |
| typename (benign) | 200 | 0.09 | 0.90 | 0.28 | 0.01 | 0.13 |
| variables (benign) | 200 | 0.03 | 0.88 | 0.18 | 0.00 | 0.09 |
| wide_selection | 130 | 0.85 | 1.00 | 0.99 | 1.00 | 1.00 |

## False positives on real benign queries (n=208)
Source: NL2GQL_Testset_V20.1 (cleaned_query, de-duplicated by skeleton)

| Method | False-positive rate |
|---|---|
| Hard limits only | 0.000 |
| Depth/cost threshold | 0.250 |
| Rule scorer | 0.000 |
| ML classifier | 0.062 |
| Combined (production) | 0.034 |

## Generalisation: leave-one-attack-category-out
Leave-one-attack-category-out: the ML model is retrained without the category and scored on that category's held-out test operations.

| Held-out category | n | ML recall | Rules recall | Combined recall | ML FPR | Combined FPR |
|---|---|---|---|---|---|---|
| alias_batching | 200 | 1.00 | 0.84 | 1.00 | 0.002 | 0.237 |
| credential_stuffing | 144 | 1.00 | 1.00 | 1.00 | 0.002 | 0.237 |
| deep_nesting | 200 | 0.53 | 0.81 | 0.67 | 0.002 | 0.237 |
| directive_overload | 200 | 0.40 | 0.75 | 0.82 | 0.002 | 0.237 |
| field_duplication | 199 | 0.00 | 0.74 | 0.54 | 0.003 | 0.237 |
| fragment_bomb | 200 | 0.55 | 1.00 | 1.00 | 0.002 | 0.237 |
| fragment_depth | 200 | 1.00 | 1.00 | 1.00 | 0.002 | 0.237 |
| introspection | 164 | 0.19 | 1.00 | 0.30 | 0.003 | 0.237 |
| list_amplification | 200 | 0.01 | 0.84 | 0.72 | 0.002 | 0.237 |
| sensitive_enumeration | 200 | 1.00 | 0.98 | 1.00 | 0.003 | 0.237 |
| wide_selection | 130 | 0.00 | 0.99 | 0.85 | 0.000 | 0.236 |

## ML blend weight (effective: 0.4)
Chosen by pooled leave-one-attack-category-out F1 on the validation split.

| ML weight | Val LOCO F1 | Precision | Recall | FPR |
|---|---|---|---|---|
| 0.0 | 0.771 | 0.683 | 0.886 | 0.370 |
| 0.2 | 0.776 | 0.707 | 0.859 | 0.320 |
| 0.4 | 0.792 | 0.767 | 0.819 | 0.225 |
| 0.6 | 0.777 | 0.797 | 0.758 | 0.174 |
| 0.8 | 0.778 | 0.797 | 0.759 | 0.174 |
| 1.0 | 0.778 | 0.797 | 0.759 | 0.174 |

## Confirmation on an independent dataset (seed 2718, n=20918, 47% abusive)
Independently generated (different seed); operations sharing a skeleton with the training split were removed. No threshold, weight or model choice used this set. Removed 491 overlapping operations.

| Method | Precision | Recall | F1 | FPR | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| Hard limits only | 0.766 | 0.387 | 0.514 | 0.106 | - | - |
| Depth/cost threshold | 0.517 | 0.946 | 0.668 | 0.797 | - | - |
| Rule scorer | 0.680 | 0.894 | 0.773 | 0.379 | 0.819 | 0.735 |
| ML classifier | 0.997 | 0.998 | 0.998 | 0.003 | 1.000 | 1.000 |
| Combined (production) | 0.789 | 0.995 | 0.880 | 0.239 | 0.875 | 0.773 |

## Gateway overhead
p50 12.31 ms, p95 26.49 ms per proxied request (framework baseline p50 2.3 ms); 59.0 req/s at concurrency 16. In-process ASGI client, stub upstream (0 ms), SQLite event write per request; single process.

## Model selection (validation)

Selected by pooled leave-one-attack-category-out (LOCO) F1 on the validation split; latency breaks ties.

| Candidate | Val PR-AUC (in-distribution) | Val LOCO F1 | LOCO recall | LOCO FPR | Single-row predict (us) |
|---|---|---|---|---|---|
| logistic_regression | 0.9513 | 0.140 | 0.083 | 0.092 | 1503 |
| random_forest | 1.0000 | 0.685 | 0.522 | 0.001 | 11371 |
| hist_gradient_boosting (selected) | 1.0000 | 0.688 | 0.526 | 0.002 | 4560 |

Production-path check: vectorised evaluation agrees with `GraphQLGateway.evaluate` on 100.0% of 400 sampled operations.

## Limitations

- Operations are synthetic, drawn from one fictional schema; labels follow generator intent, not observed attacker behaviour. Results do not predict accuracy on production traffic.
- Attack parameter ranges overlap benign ranges by design, so some errors are irreducible; benign heavy reports and mild attacks look alike at the feature level.
- Rules and generator were written by the same author, so rule recall on in-distribution categories is optimistic; the leave-one-category-out table is the better generalisation signal.
- The real-world benign set (NL2GQL test queries) measures false positives only; it contains no attacks.
- Behavioural features (rate, repetition) and the rate limiters are not part of this offline evaluation.
- Latency figures come from a single development machine and a stub upstream.
- Design-level selection bias: the generator ranges, rule thresholds and default cost limit were revised twice after reviewing aggregate results of earlier runs. The independent confirmation set guards against overfitting to specific samples, not against this; treat the numbers as a development benchmark rather than a blind validation.

Environment: Python 3.13.13, scikit-learn 1.9.0, Windows-11-10.0.26300-SP0, Intel64 Family 6 Model 191 Stepping 2, GenuineIntel (16 logical cores).
