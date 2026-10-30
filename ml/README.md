# ML pipeline

```bash
pip install -r ml/requirements.txt
python -m ml.run --seed 42        # dataset -> model selection -> evaluation -> ml/reports/* and the shipped model
python -m ml.run --per-category 40 --confirm-seed 0 --no-save-model --skip-bench   # quick smoke run
```

| Path | Purpose |
|---|---|
| `dataset/generator.py`, `dataset/build.py` | Synthetic operation generator, de-duplication, splits ([dataset card](DATASET_CARD.md)) |
| `train.py` | Candidate models, selection by leave-one-attack-category-out F1, checksummed artifact ([model card](MODEL_CARD.md)) |
| `loco.py` | Leave-one-attack-category-out scoring shared by selection and evaluation |
| `evaluate.py`, `run.py` | Baselines, metrics, confirmation set, gateway overhead, reports and plots |
| `reports/` | `evaluation.json` (served to the dashboard), `evaluation.md`, `dataset.json`, plots |
| `data/processed/NL2GQL_Testset_V20.1.parquet` | Real benign queries used only for false-positive measurement |
| `data/generated/` | Cached generated datasets (git-ignored) |

Methodology and interpretation: [docs/evaluation.md](../docs/evaluation.md).
