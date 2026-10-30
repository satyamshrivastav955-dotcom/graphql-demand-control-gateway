# Third-party notices

The [MIT licence](LICENSE) covers the source code, documentation and generated reports written for this project.
It does **not** relicense third-party material listed here.

## Dependencies

Direct runtime and build dependencies are under permissive licences compatible with MIT, checked from their package
metadata on 2026-10-29: MIT (FastAPI, Pydantic, graphql-core, PyYAML, React, React DOM, React Router, Tailwind CSS,
Vite, Vitest), BSD-3-Clause (Uvicorn, httpx, scikit-learn, joblib, pandas, NumPy), Apache-2.0 (pyarrow, TypeScript),
ISC (lucide-react), MPL-2.0 (axe-core, used only by the dashboard tests, not shipped) and the Matplotlib licence (PSF-based, used only by the offline evaluation scripts).
Transitive dependencies were not audited licence-by-licence.

## Data: `ml/data/processed/NL2GQL_Testset_V20.1.parquet`

A test set of natural-language-to-GraphQL queries over 13 databases, used only to measure false positives.
Its original source and licence have **not been verified** for the exact file in this repository. A public benchmark
with a similar shape, [stepzen-dev/NL2GQL](https://github.com/stepzen-dev/NL2GQL), states its data is available under the
MIT licence, but this repository has not confirmed that this file comes from it. Until the provenance is confirmed:

* this file is excluded from the MIT grant above;
* if they derive from that benchmark, its copyright notice and MIT licence text must accompany them;
* if their licence cannot be established, remove them (the evaluation then skips the real-query check).

## Generated data

Synthetic operations produced by `ml/dataset/generator.py` are original to this project (MIT).
