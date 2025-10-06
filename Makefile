PY ?= python
PKG ?= src/adhash
CLI ?= $(PY) -m hashmap_cli

.PHONY: setup lint type test cov smoke validate precommit fmt release \
	publish-testpypi publish-pypi \
	docker-build docker-build-dev docker-run docker-compose-up docker-compose-down

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
	$(CLI) generate-csv --outfile runs/smoke.csv --ops 2000 --read-ratio 0.7 --key-skew 0.2 --key-space 500 --seed 7
	$(CLI) --mode adaptive run-csv --csv runs/smoke.csv --metrics-out-dir runs
	$(PY) scripts/validate_metrics_ndjson.py runs/metrics.ndjson

validate:
	$(PY) scripts/validate_metrics_ndjson.py runs/metrics.ndjson

precommit:
	pre-commit run --all-files

fmt:
	black .
	ruff check . --fix

release:
	rm -rf dist
	VERSION=$$($(PY) -c "import pathlib, tomllib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print(data['project']['version'])") ; \
		towncrier build --yes --skip-if-empty --version "$$VERSION" ; \
		$(PY) scripts/build_release_artifacts.py --outdir dist ; \
		$(PY) -m twine check dist/*

publish-testpypi: release
	@if [ -z "$$TWINE_USERNAME" ] || [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Set TWINE_USERNAME=__token__ and TWINE_PASSWORD=<TestPyPI token> before running make publish-testpypi" ; \
		exit 1 ; \
	fi
	$(PY) -m twine upload --repository testpypi --skip-existing dist/*

publish-pypi: release
	@if [ -z "$$TWINE_USERNAME" ] || [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Set TWINE_USERNAME=__token__ and TWINE_PASSWORD=<PyPI token> before running make publish-pypi" ; \
		exit 1 ; \
	fi
	$(PY) -m twine upload dist/*

docker-build:
	docker build -t adaptive-hashmap-cli:local -f docker/Dockerfile .

docker-build-dev:
	docker build -t adaptive-hashmap-cli:dev -f docker/Dockerfile.dev .

docker-run:
	docker run --rm \
		-p ${ADHASH_METRICS_PORT:-9090}:${ADHASH_METRICS_PORT:-9090} \
		-e ADHASH_METRICS_PORT=${ADHASH_METRICS_PORT:-9090} \
		adaptive-hashmap-cli:local serve --host 0.0.0.0 --port ${ADHASH_METRICS_PORT:-9090}

docker-compose-up:
	docker compose -f docker/docker-compose.yml up --build

docker-compose-down:
	docker compose -f docker/docker-compose.yml down
