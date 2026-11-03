# Decisions

Format: date, decision, why, consequence.

## 2026-11-02 D1: Bump runtime pins except scikit-learn and numpy
* Bumped: fastapi 0.141.1 to 0.162.0, uvicorn 0.52.1 to 0.54.0, pydantic 2.13.4 to 2.14.2, graphql-core 3.2.12 to
  3.3.1, joblib 1.5.3 to 1.6.0. Checked against PyPI on this date. 126 tests pass, ruff clean, model loads.
* Not bumped: scikit-learn 1.9.0 (1.9.1 exists) and numpy 2.2.6 (2.5.4 exists). The shipped `risk_model.joblib` is a
  pickle from 1.9.0; under 1.9.1 sklearn emits `InconsistentVersionWarning` and the gateway's strict loader
  disabled the model in a test (`-W error`). Upgrading means retraining and changing the shipped model and its
  reported numbers, so it is deferred to Phase 6 where the ML gain is re-measured anyway.
* Consequence: sklearn and numpy remain behind latest until Phase 6.

## 2026-11-02 D2: Do not change the product name yet
* The working tree has an uncommitted rename to "GraphQL Demand Control Gateway"; the brief says "GraphQL Sentinel".
  Left untouched pending the owner's decision.

## 2026-11-02 D3: Benchmark is the critical path
* The wedge (explainable, OWASP-mapped, measured overhead) is only defensible with a head-to-head result.
  Phases 3-5 are not started before Phase 1 results are in, because a negative result changes what is worth building.
