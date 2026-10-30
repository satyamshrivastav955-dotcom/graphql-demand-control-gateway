# Contributing

Thanks for taking an interest. This is a small project; clear, tested, honest changes are the bar.

## Set up

```bash
pip install -r backend/requirements-dev.txt        # backend + tests + ruff
pip install -r ml/requirements.txt                 # only if you touch the ML pipeline
cd dashboard && npm ci                             # dashboard
```

Run everything locally with `python scripts/dev.py` (gateway + demo upstream; prints a session token) and
`cd dashboard && npm run dev`. `make help` lists the common tasks.

## Before opening a pull request

```bash
make check          # ruff, backend tests with the coverage gate, dashboard typecheck/lint/tests/build
```

* Add or update tests with the change. Security-relevant behaviour (limits, auth, redaction, enforcement) needs a test that
  would fail without the fix.
* Keep claims true. Do not hard-code metrics; numbers shown in the UI or docs must come from `python -m ml.run`, the load
  test, or a test. If you change scoring, rules or the dataset, re-run `python -m ml.run` and commit the regenerated
  `ml/reports/` and model files together, and say in the PR what moved.
* One logical change per PR; update `CHANGELOG.md` and the relevant page in `docs/`.
* Never commit secrets, real traffic, or generated databases. `.env` and `*.db` are git-ignored.

## Style

Python: ruff (`ruff check backend ml demo scripts`), type hints on public functions, small modules. TypeScript: the
dashboard's ESLint config and strict `tsc`. Comments explain *why*, not what.

## Reporting security issues

Do not open a public issue; see [SECURITY.md](SECURITY.md).

## Licence

By contributing you agree your contribution is licensed under the [MIT licence](LICENSE).
