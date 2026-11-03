# sentinel-core

The analysis and policy engine of [GraphQL Sentinel](https://github.com/): parse a GraphQL operation, compute
fragment-aware depth, alias, field and schema-aware cost features, and return an explainable ALLOW / THROTTLE / BLOCK
decision with every rule mapped to the OWASP API Security Top 10 (2023). Depends only on `graphql-core`; the ML scorer is optional (`pip install sentinel-core[ml]`).
