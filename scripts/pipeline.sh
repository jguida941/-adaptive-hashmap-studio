#!/usr/bin/env bash
set -euo pipefail

START_TS="${START_TS:-$(date +%s)}"
export START_TS

MODE="${PIPELINE_MODE:-fast}"              # fast|full
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode)
      if [ "$#" -lt 2 ]; then
        echo "Missing value for --mode" >&2
        exit 1
      fi
      MODE="$2"
      shift 2
      ;;
    --mode=*)
      MODE="${1#--mode=}"
      shift
      ;;
    fast|full)
      MODE="$1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ "$MODE" != "fast" ] && [ "$MODE" != "full" ]; then
  echo "Invalid mode: ${MODE}. Expected 'fast' or 'full'." >&2
  exit 1
fi

if [ "${MODE}" = "fast" ]; then
  export HYPOTHESIS_PROFILE="${HYPOTHESIS_PROFILE:-dev}"
else
  export HYPOTHESIS_PROFILE="${HYPOTHESIS_PROFILE:-ci}"
fi

ART="${ART_DIR:-.artifacts}"
SRC_DIR="${SRC_DIR:-src}"
TESTS_DIR="${TESTS_DIR:-tests}"
COV_MIN="${COV_MIN:-90}"
MUT_MIN="${MUT_MIN:-85}"
USE_XDIST="${USE_XDIST:-}"                 # set to 1 to enable xdist in fast mode
PYTEST_TIMEOUT="${PYTEST_TIMEOUT:-60}"
PYTEST_TIMEOUT_FULL="${PYTEST_TIMEOUT_FULL:-120}"
FAST_TEST_ARGS=()

export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export PYTHONWARNINGS="${PYTHONWARNINGS:-default}"
if [ -z "${UV_CACHE_DIR:-}" ]; then
  export UV_CACHE_DIR="$(pwd)/.uv_cache"
fi
mkdir -p "${UV_CACHE_DIR}"

mkdir -p "${ART}/logs" "${ART}/reports/covdata" "${ART}/htmlcov"
trap 'rm -rf "${ART}/smoke"' EXIT

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

PYTEST_HAS_TIMEOUT=0
PYTEST_HAS_XDIST=0
if command_exists python; then
  if python - <<'PY' >/dev/null 2>&1
import importlib.util
import sys

spec = importlib.util.find_spec("pytest_timeout")
if spec is None:
    sys.exit(1)
PY
  then
    PYTEST_HAS_TIMEOUT=1
  fi
  if python - <<'PY' >/dev/null 2>&1
import importlib.util
import sys

spec = importlib.util.find_spec("xdist")
if spec is None:
    sys.exit(1)
PY
  then
    PYTEST_HAS_XDIST=1
  fi
fi

COVERAGE_BIN=(coverage)
if ! command_exists coverage; then
  COVERAGE_BIN=(python -m coverage)
fi

copy_cov_data() {
  find . -maxdepth 1 -name ".coverage*" -print0 | while IFS= read -r -d '' file; do
    cp "$file" "${ART}/reports/covdata/$(basename "$file")"
  done || true
}

run_cov_reports() {
  "${COVERAGE_BIN[@]}" combine || true
  "${COVERAGE_BIN[@]}" xml -o "${ART}/coverage.xml"
  "${COVERAGE_BIN[@]}" html -d "${ART}/htmlcov"
  "${COVERAGE_BIN[@]}" report --fail-under "${COV_MIN}"
}

maybe_uv() {
  if command_exists uv; then
    uv "$@"
    return $?
  fi
  return 127
}

build_wheel() {
  echo "== Build wheel =="
  rm -rf dist
  if ! maybe_uv build -o dist >/dev/null 2>&1; then
    if ! command_exists python; then
      echo "python not found" >&2
      exit 1
    fi
    if ! python -m build --version >/dev/null 2>&1; then
      python -m pip install --quiet build
    fi
    python -m build --wheel --outdir dist
  fi
}

wheel_smoke() {
  build_wheel
  python -m venv "${ART}/smoke"
  # shellcheck disable=SC1091
  . "${ART}/smoke/bin/activate"
  python -m pip install -U pip >/dev/null
  pip install dist/*.whl

  python - <<'PY'
import importlib
import os
import sys
names = [os.environ.get("PKG_IMPORT_NAME"), os.environ.get("PKG_ALT_IMPORT_NAME")]
names = [n for n in names if n]
if not names:
    sys.exit(0)
for name in names:
    try:
        module = importlib.import_module(name)
        print(f"[smoke] Imported {name}; version=", getattr(module, "__version__", "unknown"))
        break
    except Exception as exc:
        print(f"[smoke] Import {name} failed: {exc}", file=sys.stderr)
else:
    sys.exit("No import name succeeded")
PY

  local cli_name="${PKG_CLI_NAME:-}"
  local cli_required="${PKG_CLI_REQUIRED:-0}"
  if [ -z "${cli_name}" ] && [ "${RUN_CLI_SMOKE:-0}" != "0" ]; then
    cli_name="hashmap-cli"
  fi
  if [ -n "${cli_name}" ]; then
    if command -v "${cli_name}" >/dev/null 2>&1; then
      if ! "${cli_name}" --help >/dev/null; then
        echo "[smoke] ${cli_name} --help failed" >&2
        if [ "${cli_required}" = "1" ]; then
          exit 1
        else
          echo "[smoke] Continuing despite CLI help failure (PKG_CLI_REQUIRED=1 to enforce)" >&2
        fi
      fi
    else
      echo "[smoke] CLI '${cli_name}' not found on PATH; skipping CLI smoke" >&2
      if [ "${cli_required}" = "1" ]; then
        exit 1
      fi
    fi
  else
    echo "[smoke] CLI smoke check skipped (set PKG_CLI_NAME or RUN_CLI_SMOKE to enable)" >&2
  fi

  deactivate || true
}

derive_diff_scope() {
  if [ -n "${CHANGED_PY:-}" ]; then
    return
  fi
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    CHANGED_PY=""
    return
  fi

  local base="origin/main"
  if [ -n "${GITHUB_BASE_REF:-}" ]; then
    base="origin/${GITHUB_BASE_REF}"
  fi
  local head="${GITHUB_HEAD_REF:-HEAD}"

  if git show-ref --verify --quiet "refs/remotes/${base}"; then
    CHANGED_PY=$(git diff --name-only "${base}"..."${head}" | grep -E '^(src|tests)/.*\.py$' || true)
  else
    if git rev-parse HEAD~1 >/dev/null 2>&1; then
      CHANGED_PY=$(git diff --name-only HEAD~1...HEAD | grep -E '^(src|tests)/.*\.py$' || true)
    else
      CHANGED_PY=""
    fi
  fi
}

write_changed_files() {
  if [ -n "${CHANGED_PY:-}" ]; then
    printf "%s\n" "$CHANGED_PY" > "${ART}/logs/changed_files.txt"
  else
    : > "${ART}/logs/changed_files.txt"
  fi
}

build_fast_test_expr() {
  FAST_TEST_ARGS=()
  if [ -z "${CHANGED_PY:-}" ]; then
    return
  fi
  mapfile -t _fast_tests < <(printf "%s\n" "$CHANGED_PY" | grep '^tests/.*\.py$' || true)
  if [ ${#_fast_tests[@]} -gt 0 ]; then
    FAST_TEST_ARGS=("${_fast_tests[@]}")
  fi
}

compute_mutate_packages() {
  if [ -n "${MUTATE_PACKAGES:-}" ]; then
    MUTATE_PACKAGES=$(
      python - "$SRC_DIR" <<'PY'
import os
import sys

src_dir = sys.argv[1].rstrip("/")
raw = os.environ.get("MUTATE_PACKAGES", "")
packages = set()
for token in raw.split(","):
    token = token.strip()
    if not token:
        continue
    if token.startswith(src_dir + "/"):
        token = token[len(src_dir) + 1 :]
    elif token.startswith(src_dir):
        token = token[len(src_dir) :].lstrip("/")
    head = token.split("/", 1)[0]
    if head:
        packages.add(head)
if packages:
    print(",".join(f"{src_dir}/{name}" for name in sorted(packages)))
PY
    )
    return
  fi

  if [ -z "${CHANGED_PY:-}" ]; then
    MUTATE_PACKAGES=""
    return
  fi

  MUTATE_PACKAGES=$(
    printf "%s\n" "$CHANGED_PY" | python - "$SRC_DIR" <<'PY'
import sys

src_dir = sys.argv[1].rstrip("/")
prefix = f"{src_dir}/"
packages = set()
for line in sys.stdin:
    line = line.strip()
    if not line.startswith(prefix):
        continue
    head = line[len(prefix) :].split("/", 1)[0]
    if head:
        packages.add(head)
if packages:
    print(",".join(f"{src_dir}/{name}" for name in sorted(packages)))
PY
  )
}

resolve_default_mutmut_target() {
  if [ -n "${MUTMUT_FALLBACK_PATH:-}" ]; then
    printf "%s" "${MUTMUT_FALLBACK_PATH}"
    return
  fi

  python - "$SRC_DIR" <<'PY'
import sys
from pathlib import Path

src_dir = Path(sys.argv[1])
if not src_dir.is_dir():
    sys.exit(0)

package_candidates = []
module_candidates = []

for entry in sorted(src_dir.iterdir()):
    if entry.name.startswith(("_", ".")):
        continue
    if entry.is_dir() and (entry / "__init__.py").exists():
        package_candidates.append(entry)
    elif entry.is_file() and entry.suffix == ".py":
        module_candidates.append(entry)

chosen = package_candidates[0] if package_candidates else (module_candidates[0] if module_candidates else None)
if chosen:
    print(str(chosen))
PY
}

run_lint_and_types() {
  local ruff_cmd=()
  local mypy_cmd=()

  if [ -x ".venv/bin/ruff" ]; then
    ruff_cmd=(".venv/bin/ruff")
  elif command_exists ruff; then
    ruff_cmd=(ruff)
  elif command_exists uv; then
    ruff_cmd=(uv run ruff)
  fi

  if [ -x ".venv/bin/mypy" ]; then
    mypy_cmd=(".venv/bin/mypy")
  elif command_exists mypy; then
    mypy_cmd=(mypy)
  elif command_exists uv; then
    mypy_cmd=(uv run mypy)
  fi

  if [ ${#ruff_cmd[@]} -gt 0 ]; then
    "${ruff_cmd[@]}" check . --force-exclude --respect-gitignore
    "${ruff_cmd[@]}" format --check .
  else
    echo "ruff not found; skipping lint" >&2
  fi

  if [ ${#mypy_cmd[@]} -gt 0 ]; then
    "${mypy_cmd[@]}" --config-file mypy.ini "$SRC_DIR" "$TESTS_DIR"
  else
    echo "mypy not found; skipping type check" >&2
  fi
}

pytest_fast_selection() {
  "${COVERAGE_BIN[@]}" erase || true
  local cmd=("${COVERAGE_BIN[@]}" run -m pytest)
  if [ "$USE_XDIST" = "1" ] && [ "${PYTEST_HAS_XDIST}" = "1" ]; then
    cmd+=( -n auto )
  elif [ "$USE_XDIST" = "1" ]; then
    echo "[pytest] pytest-xdist plugin not available; running without -n (fast suite)" >&2
  fi
  local mark_expr_default="${FAST_MARK_EXPR:-unit and not flaky and not slow}"
  local mark_expr="${mark_expr_default}"
  local fallback_mark="${FAST_MARK_FALLBACK:-not flaky and not slow}"
  if ! python -m pytest --collect-only -q -m "$mark_expr" >/dev/null 2>&1; then
    if [ "$mark_expr" != "$fallback_mark" ]; then
      echo "[FAST] no tests found for marker '${mark_expr}'; falling back to '${fallback_mark}'"
      mark_expr="$fallback_mark"
    fi
  fi
  local pytest_args=(-q --maxfail=1 --durations=20 --junitxml "${ART}/junit.xml" -m "$mark_expr")
  if [ "${PYTEST_HAS_TIMEOUT}" = "1" ]; then
    pytest_args+=( --timeout "${PYTEST_TIMEOUT}" --timeout-method=signal )
  else
    echo "[pytest] pytest-timeout plugin not available; running without --timeout (fast suite)" >&2
  fi
  cmd+=( "${pytest_args[@]}" )
  if [ ${#FAST_TEST_ARGS[@]} -gt 0 ]; then
    cmd+=( "${FAST_TEST_ARGS[@]}" )
  fi
  echo "== FAST: unit/property tests =="
  "${cmd[@]}"
  copy_cov_data
}

pytest_full_suite() {
  "${COVERAGE_BIN[@]}" erase || true
  local cmd=("${COVERAGE_BIN[@]}" run -m pytest)
  if [ "${USE_XDIST:-1}" != "0" ] && [ "${PYTEST_HAS_XDIST}" = "1" ]; then
    cmd+=( -n auto )
  elif [ "${USE_XDIST:-1}" != "0" ]; then
    echo "[pytest] pytest-xdist plugin not available; running without -n (full suite)" >&2
  fi
  local pytest_args=(-q --maxfail=1 --durations=20 --junitxml "${ART}/junit.xml" -m "not flaky")
  if [ "${PYTEST_HAS_TIMEOUT}" = "1" ]; then
    pytest_args+=( --timeout "${PYTEST_TIMEOUT_FULL}" --timeout-method=signal )
  else
    echo "[pytest] pytest-timeout plugin not available; running without --timeout (full suite)" >&2
  fi
  cmd+=( "${pytest_args[@]}" )
  echo "== FULL: complete suite =="
  "${cmd[@]}"
  copy_cov_data
}

mutation_stage() {
  echo "== Mutation testing =="
  if ! command_exists mutmut; then
    echo "mutmut not installed; install it via 'uv pip install mutmut'" >&2
    exit 1
  fi
  if [ "$MODE" = "fast" ]; then
    if [ -n "${MUTATE_PACKAGES:-}" ]; then
      echo "[FAST] mutating touched packages: ${MUTATE_PACKAGES}"
      IFS=',' read -r -a mutate_targets <<< "${MUTATE_PACKAGES}"
      local mutmut_args=()
      for target in "${mutate_targets[@]}"; do
        target="${target//[[:space:]]/}"
        if [ -n "$target" ]; then
          mutmut_args+=( --paths-to-mutate "$target" )
        fi
      done
      if [ ${#mutmut_args[@]} -eq 0 ]; then
        local fallback_target
        fallback_target=$(resolve_default_mutmut_target | tr -d '\n')
        if [ -z "${fallback_target}" ]; then
          echo "[FAST] unable to determine fallback mutation target; set MUTMUT_FALLBACK_PATH." >&2
          exit 1
        fi
        echo "[FAST] mutating fallback target ${fallback_target} (no valid package targets detected)"
        mutmut run --paths-to-mutate "${fallback_target}" --use-coverage --timeout 30
      else
        mutmut run "${mutmut_args[@]}" --use-coverage --timeout 30
      fi
    else
      local fallback_target
      fallback_target=$(resolve_default_mutmut_target | tr -d '\n')
      if [ -z "${fallback_target}" ]; then
        echo "[FAST] unable to determine fallback mutation target; set MUTMUT_FALLBACK_PATH." >&2
        exit 1
      fi
      echo "[FAST] mutating fallback target ${fallback_target} (no touched packages detected)"
      mutmut run --paths-to-mutate "${fallback_target}" --use-coverage --timeout 30
    fi
  else
    echo "[FULL] full mutation sweep"
    mutmut run --timeout 30
  fi
  mutmut results > "${ART}/mutation_results.txt" || true
  if grep -E "survived|🙁|🤔" -q "${ART}/mutation_results.txt"; then
    echo "Mutation survivors detected:" >&2
    cat "${ART}/mutation_results.txt"
    exit 1
  fi
}

security_and_supply_chain() {
  echo "== Security & Supply Chain =="
  local vuln_high=0
  export BANDIT_HIGH=0

  if command_exists semgrep; then
    semgrep scan --config .semgrep.yml --severity ERROR --sarif --output "${ART}/semgrep.sarif" || true
  fi
  if command_exists bandit; then
    bandit -q -r "${SRC_DIR}" | tee "${ART}/bandit.txt" || true
    bandit_high=$(grep -Eci "Severity:\s*HIGH" "${ART}/bandit.txt" || true)
    export BANDIT_HIGH="${bandit_high}"
    if [ "${bandit_high}" -gt 0 ]; then
      echo "Bandit reported ${bandit_high} HIGH findings. Failing pipeline." >&2
      exit 1
    fi
  fi
  if command_exists syft; then
    syft dir:. -o cyclonedx-json > "${ART}/sbom.cdx.json" || true
  fi
  if command_exists grype; then
    if [ -f "${ART}/sbom.cdx.json" ]; then
      grype sbom:"${ART}/sbom.cdx.json" -o json > "${ART}/grype.json" || true
    else
      grype dir:. -o json > "${ART}/grype.json" || true
    fi
  fi
  if command_exists trivy; then
    trivy fs -f json -o "${ART}/trivy.json" . || true
  fi
  if command_exists pip-audit; then
    pip-audit -f json -o "${ART}/pip-audit.json" || true
  fi

  if [ -f "${ART}/grype.json" ]; then
    vuln_high=$((vuln_high + $(grep -Eoc '"severity"\s*:\s*"High"|"severity"\s*:\s*"Critical"' "${ART}/grype.json" || true)))
  fi
  if [ -f "${ART}/trivy.json" ]; then
    vuln_high=$((vuln_high + $(grep -Eoc '"Severity"\s*:\s*"HIGH"|"Severity"\s*:\s*"CRITICAL"' "${ART}/trivy.json" || true)))
  fi
  if [ -f "${ART}/pip-audit.json" ]; then
    local pip_audit_high=0
    if command_exists jq; then
      pip_audit_high=$(jq -r '
        [
          (if type == "array" then .[] else (.dependencies // [])[] end)
          | (.vulns // [])[]?
          | (.severity // "") as $sev
          | ( $sev | ascii_upcase )
          | select(. == "HIGH" or . == "CRITICAL")
        ]
        | length
      ' "${ART}/pip-audit.json" 2>/dev/null || true)
    else
      pip_audit_high=$(python - "${ART}/pip-audit.json" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except FileNotFoundError:
    print(0)
    raise SystemExit

def iter_dependencies(payload):
    if isinstance(payload, list):
        yield from payload
    else:
        yield from payload.get("dependencies", [])

count = 0
for dep in iter_dependencies(data):
    for vuln in dep.get("vulns", []):
        severity = (vuln.get("severity") or "").upper()
        if severity in {"HIGH", "CRITICAL"}:
            count += 1
print(count)
PY
      )
    fi
    pip_audit_high=${pip_audit_high:-0}
    vuln_high=$((vuln_high + pip_audit_high))
  fi

  export VULN_HIGH="${vuln_high}"
  if [ "${vuln_high}" -gt 0 ]; then
    echo "HIGH/CRITICAL vulnerabilities detected (${vuln_high}). Failing pipeline." >&2
    exit 1
  fi
}

main() {
  echo "== Mode: ${MODE} =="
  derive_diff_scope
  write_changed_files
  build_fast_test_expr
  compute_mutate_packages

  run_lint_and_types
  wheel_smoke

  if [ "${MODE}" = "fast" ]; then
    pytest_fast_selection
  else
    pytest_full_suite
  fi
  run_cov_reports

  security_and_supply_chain
  mutation_stage

  local end_ts="$(date +%s)"
  PIPELINE_MINUTES=$(awk -v d="$((end_ts-START_TS))" 'BEGIN{printf("%.1f", d/60.0)}')
  export PIPELINE_MINUTES
  export PIPELINE_MODE="${MODE}"

  scripts/ci_summary.sh "${ART}" || true

  echo "== Pipeline completed in ${PIPELINE_MINUTES} minutes =="
}

main "$@"
