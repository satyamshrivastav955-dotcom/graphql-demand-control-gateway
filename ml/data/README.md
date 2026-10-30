# Data

* `processed/NL2GQL_Testset_V20.1.parquet`: the NL2GQL test set (real
  natural-language-to-GraphQL queries over 13 databases). Only the `cleaned_query` column is used, as a set of real
  benign queries for false-positive measurement. Check the benchmark's own licence before redistributing.
* `generated/`: synthetic datasets written by `python -m ml.run` (git-ignored, reproducible from the seed).
