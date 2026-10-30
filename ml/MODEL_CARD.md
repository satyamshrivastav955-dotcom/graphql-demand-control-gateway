# Model card: sentinel-risk classifier

| | |
|---|---|
| Artifact | `backend/core/models/risk_model.joblib` (+ `risk_model.json` with SHA-256, feature list, selection results) |
| Task | Binary: is this GraphQL operation an abuse pattern (1) or ordinary traffic (0)? |
| Input | The 16 numeric features from `backend/core/analysis/analyzer.py` (`FEATURE_NAMES`) |
| Algorithm | Chosen at training time among logistic regression, random forest and histogram gradient boosting (currently `hist_gradient_boosting`) |
| Training data | Training split of the synthetic dataset v1.0 ([dataset card](DATASET_CARD.md)), seed 42 |
| Selection | Pooled leave-one-attack-category-out F1 on the validation split; latency breaks ties |
| Use in the gateway | Second opinion blended with rule scores (`docs/scoring.md`); never the sole decision-maker; absent or tampered model → rules only |
| Reproduce | `python -m ml.run --seed 42` |

## Intended use

Prioritising GraphQL operations for throttling/blocking alongside deterministic limits, in a gateway that logs and
explains every decision.

## Not suitable for

* Standing alone as a security control.
* APIs whose legitimate traffic differs strongly from the synthetic benign classes without re-training and
  re-evaluating on that API's own traffic.
* Detecting attacks that are not visible in the operation text (authorisation flaws, resolver injection).

## Performance and limits

See [`ml/reports/evaluation.md`](reports/evaluation.md). Headline caveat: in-distribution scores are near-perfect
because the model learns the generator's structure; when an entire abusive category is withheld from training,
recall falls sharply for several categories. The weight given to the model in the blend reflects that.

## Loading and integrity

The artifact is a pickle (joblib). The gateway refuses to load it unless the file's SHA-256 and the feature list in
`risk_model.json` match, and it requires the scikit-learn version pinned in `backend/requirements.txt`. Never load a
model file from an untrusted source.
