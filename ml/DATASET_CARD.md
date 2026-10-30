# Dataset card: Sentinel synthetic GraphQL operations v1.0

**Purpose.** Train and evaluate detectors for operation-level GraphQL abuse. **Not** a record of real attacks.

**Generation.** `ml/dataset/generator.py` random-walks a fictional e-commerce/social schema (10 types, cyclic
relations) and renders operations with varied formatting (pretty/compact), arguments, variables, aliases,
fragments, directives and mutations. Regenerate with `python -m ml.run --rebuild-dataset` (seeded; default seed 42).

| Class | Categories |
|---|---|
| Benign (label 0) | lookup, list_page, nested_view, dashboard, fragment_reuse, mutation, login, heavy_report, typename, variables, conditional_fields, full_profile |
| Abusive (label 1) | deep_nesting, alias_batching, field_duplication, fragment_bomb, fragment_depth, directive_overload, introspection, sensitive_enumeration, list_amplification, credential_stuffing, wide_selection |

**Labels** reflect generator intent ("this pattern is abusive"), not observed attacker behaviour or the output of
any detector. Parameter ranges of benign and abusive categories deliberately overlap (e.g. dashboards with up to
14 aliases vs alias batching from 6; nested views to depth 9 vs deep nesting from 6), using log-uniform draws so
mild cases are common.

**Splits.** Operations are de-duplicated by *skeleton* (literals and whitespace stripped) before splitting, so no
skeleton appears twice. 60/20/20 train/validation/test, stratified by category. Sizes and per-category counts:
`ml/reports/dataset.json`. A second dataset from another seed (the "confirmation" set) is scored once per run;
operations whose skeleton appears in the training data are removed from it.

**Real-world benign set.** 208 de-duplicated queries from `ml/data/processed/NL2GQL_Testset_V20.1.parquet`
(`cleaned_query`; 13 databases) are used only to measure false positives. They contain no attacks. Source and
licence of that test set: see the provenance of the NL2GQL benchmark; it is included here for evaluation only.

**Known limitations.**
* One schema, one author: the classifier can learn the generator's structural signatures. In-distribution scores are
  therefore a ceiling, and the leave-one-category-out results are the more informative measure.
* No behavioural/time-series signals, no authentication context, no real attacker payloads.
* The benign class includes deliberately heavy hard negatives, so false-positive rates on it are a stress test,
  not an estimate of production false-positive rates.
