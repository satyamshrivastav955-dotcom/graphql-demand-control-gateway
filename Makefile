.PHONY: help install dev test lint typecheck dashboard-check check ml loadtest openapi demo-samples clean

help:  ## List common tasks
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

install:  ## Install backend dev dependencies and dashboard packages
	pip install -r backend/requirements-dev.txt
	cd dashboard && npm ci

dev:  ## Run demo upstream + gateway (prints a session token); dashboard: cd dashboard && npm run dev
	python scripts/dev.py

lint:  ## Ruff
	ruff check backend ml demo scripts

test:  ## Backend tests with the coverage gate used in CI
	python -m pytest --cov=backend --cov-report=term-missing --cov-fail-under=85

dashboard-check:  ## Dashboard typecheck, lint, tests, production build
	cd dashboard && npm run typecheck && npm run lint && npm test && npm run build

check: lint test dashboard-check  ## Everything CI runs (except the Docker job)

ml:  ## Rebuild dataset, retrain, evaluate, regenerate ml/reports and the shipped model (minutes)
	python -m ml.run --seed 42

demo-samples:  ## Re-record the landing page's demo samples from the shipped engine
	python scripts/export_demo_samples.py

loadtest:  ## Start a private gateway and measure throughput/latency
	python scripts/loadtest.py --duration 20 --concurrency 32

openapi:  ## Regenerate docs/openapi.json
	python scripts/export_openapi.py

clean:  ## Remove build output and caches
	rm -rf dashboard/dist .pytest_cache .ruff_cache .coverage
