PY ?= python
PKG ?= src/adhash
CLI ?= $(PY) -m hashmap_cli

.PHONY: setup lint type test cov smoke validate precommit fmt release \
    publish-testpypi publish-pypi \
    docker-build docker-build-dev docker-run docker-compose-up docker-compose-down \
    mutants-report mutants-report-local mutants-worktrees mutants-run-lanes \
    mutants-auto mutants-dryrun mutants-core

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

MUTANTS_WORKFLOW ?= mutmut.yml
MUTANTS_ARTIFACT ?= mutmut-results
MUTANTS_TOPN ?= 25
MUTANTS_REPORT_DEST ?= file

mutants-report:
	: ${WORKFLOW:=$(MUTANTS_WORKFLOW)}
	: ${ART_NAME:=$(MUTANTS_ARTIFACT)}
	: ${TOPN:=$(MUTANTS_TOPN)}
	: ${REPORT_DEST:=$(MUTANTS_REPORT_DEST)}
	WORKFLOW=${WORKFLOW} ART_NAME=${ART_NAME} TOPN=${TOPN} REPORT_DEST=${REPORT_DEST} \
		tools/mutants_report.sh

mutants-report-local:
	: ${TOPN:=$(MUTANTS_TOPN)}
	: ${REPORT_DEST:=stdout}
	MUTANTS_LOCAL_ONLY=1 TOPN=${TOPN} REPORT_DEST=${REPORT_DEST} tools/mutants_report.sh

# ---------------------------------------------------------------------------
# Mutation worktree helpers
# ---------------------------------------------------------------------------

MUTANT_LANES ?= maps=src/adhash/core/maps.py probing=src/adhash/core/probing.py snapshot=src/adhash/core/snapshot.py
MUTANT_TIMEOUT ?= 8
MUTANT_JOBS ?= auto

mutants-worktrees:
	mkdir -p worktrees
	@for lane in $(MUTANT_LANES); do \
		name=$${lane%%=*}; \
		printf '[mutants] ensuring worktree %s\n' $$name; \
		git worktree add -f worktrees/$$name main >/dev/null 2>&1 || true; \
	done

mutants-run-lanes: mutants-worktrees
	@for lane in $(MUTANT_LANES); do \
		name=$${lane%%=*}; \
		paths=$${lane#*=}; \
		printf '[mutants] running lane %s (paths=%s)\n' $$name $$paths; \
		( cd worktrees/$$name && \
		  mutmut run --paths-to-mutate "$$paths" --use-coverage --jobs $(MUTANT_JOBS) --timeout $(MUTANT_TIMEOUT) ); \
		( cd worktrees/$$name && \
		  tools/mutants_report.sh WORKFLOW=mutation-tests.yml ART_NAME=mutmut-results \
		    MUTANTS_LOCAL_ONLY=1 REPORT_DEST=file SKIP_MUTMUT_INSTALL=1 ); \
	done

mutants-auto:
	tools/mutants_orchestrator.sh --module src/adhash/core/maps.py --target-kill 0.70 --survivors-cap 50 --max-iterations 3 --timeout 8 --topn 25

mutants-dryrun:
	tools/mutants_orchestrator.sh --module src/adhash/core/maps.py --target-kill 0.70 --survivors-cap 50 --max-iterations 1 --timeout 8 --topn 25 --dry-run

mutants-core:
	@for mod in src/adhash/core/maps.py src/adhash/core/probing.py src/adhash/core/snapshot.py; do \
		tools/mutants_orchestrator.sh --module $$mod --target-kill 0.70 --survivors-cap 50 --max-iterations 2 --timeout 8 --topn 25; \
	done
