# Scoring and decisions

## Features

`backend/core/analysis/analyzer.py` analyses the operation the server would execute (selected by `operationName`),
with fragment spreads resolved.

| Feature | Meaning |
|---|---|
| `max_depth` | Deepest field nesting (fragment spreads do not add depth, the fields inside them do) |
| `field_count` | Fields after resolving fragments (saturates at 10⁹ for fragment bombs) |
| `alias_count`, `duplicate_field_count` | Aliased fields; repeated selections of the same response key |
| `fragment_count`, `fragment_spread_count`, `directive_count` | Fragment definitions, spreads, directives |
| `introspection_score` | `__schema` / `__type` fields (`__typename` is **not** introspection) |
| `sensitive_field_count` | Field names containing `password`, `token`, `secret`, `ssn`, `email`, ... |
| `mutation_score` | 1 for mutations |
| `complexity_score` | 1 + argument count per field, multiplied by list sizes (`first`, `limit`, ... from literals or variables, capped at 1000 per level) |
| `max_list_multiplier`, `token_count`, `query_length`, `variable_count`, `operation_count` | Size signals |

## Rule score (0-100)

`backend/core/security_engine/rules.py` adds points per rule (depth, aliases, breadth, duplicates, complexity,
sensitive fields, mutation, mutation + sensitive, fragments, directives, introspection when `flag`, multi-vector
bonus, repeat flood). Each rule returns an explanation `{rule, feature, value, points, severity, description}`;
the rule score is the clamped sum of the points, so the explanation is exact rather than approximate.

## ML probability

`backend/core/models/risk_model.joblib` (+ `risk_model.json`) holds a scikit-learn classifier over the same
features. It is loaded only if its SHA-256 and feature list match the metadata. See `ml/MODEL_CARD.md`.

## Blend

```
blended = (1 - w) * rule_score + w * 100 * ml_probability
score   = max(blended, rule_score)  if rule_score > tiers.high_risk
        = blended                   otherwise
```

`w` is `security.policy.ml_weight` if set, otherwise the weight recorded with the model (chosen by pooled
leave-one-attack-category-out F1 on the validation split). Without a model, `score = rule_score`.

## Tiers and actions

| Score | Tier | Default action |
|---|---|---|
| 0-20 | SAFE | ALLOW |
| 21-40 | LOW_RISK | ALLOW |
| 41-65 | MEDIUM_RISK | ALLOW (flagged in the dashboard) |
| 66-85 | HIGH_RISK | THROTTLE |
| 86-100 | CRITICAL | BLOCK |

Thresholds and actions are configurable. Any hard-limit violation forces BLOCK and raises the score above the
HIGH_RISK threshold.

**THROTTLE** means the operation is forwarded only while the client is within `throttle.risky_quota` such
operations per window; beyond that it receives `429` with `Retry-After`. Normal traffic from the same client is
unaffected.
