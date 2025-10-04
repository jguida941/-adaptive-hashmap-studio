PY ?= python
PKG ?= src/adhash

.PHONY: setup lint type test cov smoke validate precommit fmt

setup:
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e .[dev]
	@echo "Run 'pre-commit install' once for local hooks."

lint:
	ruff check .

type:
	mypy src tests

test:
	pytest -q

cov:
	coverage run -m pytest -q && coverage report -m

smoke:
	mkdir -p runs
	$(PY) hashmap_cli.py generate-csv --outfile runs/smoke.csv --ops 2000 --read-ratio 0.7 --key-skew 0.2 --key-space 500 --seed 7
	$(PY) hashmap_cli.py --mode adaptive run-csv --csv runs/smoke.csv --metrics-out-dir runs
	$(PY) scripts/validate_metrics_ndjson.py runs/metrics.ndjson

validate:
	$(PY) scripts/validate_metrics_ndjson.py runs/metrics.ndjson

precommit:
	pre-commit run --all-files

fmt:
	black .
	ruff check . --fix
