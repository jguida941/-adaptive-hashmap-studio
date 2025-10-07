#!/usr/bin/env bash
# Mutation orchestration loop: runs mutmut for a given module, generates survivor
# reports, optionally scaffolds TODO tests, and repeats until success criteria
# (kill-rate or survivor cap) are met or max iterations is reached.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: tools/mutants_orchestrator.sh --module <path> [options]

Options:
  --module PATH            Module/file path to mutate (required)
  --target-kill FLOAT      Kill-rate threshold (default: 0.70)
  --survivors-cap INT      Stop once survivors <= cap (default: 50)
  --max-iterations INT     Maximum loop iterations (default: 3)
  --timeout INT            Mutmut timeout in seconds (default: 8)
  --jobs N                 Mutmut --jobs value (default: auto)
  --topn INT               Top survivors to include in report (default: 25)
  --dry-run                Do not execute mutmut; write proposals only
  --mutate-arg ARG         Extra argument forwarded to mutmut (repeatable)
  --help                   Show this help text

Environment overrides mirror these flags (e.g. TARGET_KILL=0.8).
USAGE
}

# Defaults
MODULE=""
TARGET_KILL="${TARGET_KILL:-0.70}"
SURVIVORS_CAP="${SURVIVORS_CAP:-50}"
MAX_ITER="${MAX_ITER:-3}"
TIMEOUT="${MUTANT_TIMEOUT:-8}"
JOBS="${MUTANT_JOBS:-auto}"
TOPN="${TOPN:-25}"
DRY_RUN="${DRY_RUN:-0}"
declare -a MUTATE_ARGS

while (($#)); do
  case "$1" in
    --module)
      MODULE="$2"; shift 2 ;;
    --target-kill)
      TARGET_KILL="$2"; shift 2 ;;
    --survivors-cap)
      SURVIVORS_CAP="$2"; shift 2 ;;
    --max-iterations)
      MAX_ITER="$2"; shift 2 ;;
    --timeout)
      TIMEOUT="$2"; shift 2 ;;
    --jobs)
      JOBS="$2"; shift 2 ;;
    --topn)
      TOPN="$2"; shift 2 ;;
    --dry-run)
      DRY_RUN="1"; shift ;;
    --mutate-arg)
      MUTATE_ARGS+=("$2"); shift 2 ;;
    --help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1 ;;
  esac
done

if [[ -z "$MODULE" ]]; then
  echo "[mutants-orchestrator] --module is required" >&2
  usage >&2
  exit 1
fi

if [[ ! -d tests/mutation_todos ]]; then
  mkdir -p tests/mutation_todos/_proposed
else
  mkdir -p tests/mutation_todos/_proposed
fi

MUTATE_CMD=(mutmut run --paths-to-mutate "$MODULE" --use-coverage --jobs "$JOBS" --timeout "$TIMEOUT")
if ((${#MUTATE_ARGS[@]})); then
  MUTATE_CMD+=("${MUTATE_ARGS[@]}")
fi

CURRENT_KILLED=0
CURRENT_SURVIVED=0
CURRENT_KILLRATE=0
CURRENT_SURVIVORS_JSON=0

python_eval() {
  python3 - "$@"
}

run_pytest_warm() {
  echo "[mutants-orchestrator] warming coverage via pytest"
  pytest -q >/dev/null
}

run_mutmut_cycle() {
  local phase_label="$1"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[mutants-orchestrator] DRY_RUN=1 (skipping mutmut run for $phase_label)"
  else
    echo "[mutants-orchestrator] mutmut run ($phase_label)"
    "${MUTATE_CMD[@]}"
  fi

  echo "[mutants-orchestrator] generating survivor report (TOPN=$TOPN)"
  TOPN="$TOPN" REPORT_DEST="file" MUTANTS_LOCAL_ONLY=1 SKIP_MUTMUT_INSTALL=1 tools/mutants_report.sh

  parse_scoreboard
}

parse_scoreboard() {
  local summary killed survived line json_path

  summary=$(mutmut results 2>/dev/null | tail -n 100 || true)
  killed=$( { grep -Eo 'Killed\s*:\s*[0-9]+' <<<"$summary" | awk '{print $NF}' | tail -n1; } || true )
  survived=$( { grep -Eo 'Survived\s*:\s*[0-9]+' <<<"$summary" | awk '{print $NF}' | tail -n1; } || true )

  if [[ -z "$killed" || -z "$survived" ]]; then
    if [[ -f .mutmut-ci/github_step_summary.md ]]; then
      line=$(grep -E '🎉|Killed' .mutmut-ci/github_step_summary.md | tail -n1 || true)
      [[ -z "$killed" ]] && killed=$( { grep -Eo '🎉[[:space:]]*[0-9]+' <<<"$line" | awk '{print $2}' ; } || true )
      [[ -z "$survived" ]] && survived=$( { grep -Eo '🫥[[:space:]]*[0-9]+' <<<"$line" | awk '{print $2}' ; } || true )
    fi
  fi

  json_path=.mutmut-ci/survivors_report.json
  if [[ -f "$json_path" ]]; then
    CURRENT_SURVIVORS_JSON=$(JSON_PATH="$json_path" python_eval <<'PY'
import json, os
path = os.environ.get('JSON_PATH', '.mutmut-ci/survivors_report.json')
try:
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    print(len(data.get('survivors', [])))
except FileNotFoundError:
    print(0)
PY
)
  else
    CURRENT_SURVIVORS_JSON=0
  fi

  CURRENT_KILLED=${killed:-0}
  CURRENT_SURVIVED=${survived:-0}
  local total=$(( CURRENT_KILLED + CURRENT_SURVIVED ))
  CURRENT_KILLRATE=$(KILL_TOTAL="$total" KILL_COUNT="$CURRENT_KILLED" python_eval <<'PY'
import os
total = int(os.environ['KILL_TOTAL'])
killed = int(os.environ['KILL_COUNT'])
if total == 0:
    print(0)
else:
    print(round(killed/total, 4))
PY
)

  echo "[mutants-orchestrator] scoreboard :: killed=${CURRENT_KILLED} survived=${CURRENT_SURVIVED} kill-rate=${CURRENT_KILLRATE} survivors(json)=${CURRENT_SURVIVORS_JSON}"
}

write_placeholders() {
  local json_path=.mutmut-ci/survivors_report.json
  [[ -f "$json_path" ]] || return 0

  MODULE="$MODULE" DRY_RUN="$DRY_RUN" python_eval <<'PY'
import json
import os
import pathlib

json_path = '.mutmut-ci/survivors_report.json'
module = os.environ['MODULE']
dry_run = os.environ.get('DRY_RUN') == '1'

try:
    with open(json_path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
except FileNotFoundError:
    raise SystemExit

survivors = data.get('survivors') or []
if not survivors:
    raise SystemExit

destinations = []

safe_module = module.strip('/')
safe_module = safe_module.replace('/', '_').replace('.py', '')

for entry in survivors:
    file_path = entry.get('file') or ''
    if not file_path.startswith(module):
        continue
    mutant_id = entry.get('id')
    if mutant_id is None:
        continue
    summary = entry.get('summary', '')
    diff = entry.get('diff') or ''
    if dry_run:
        rel_path = pathlib.Path('tests/mutation_todos/_proposed') / f"test_{safe_module}_{mutant_id}.py.proposed"
    else:
        rel_path = pathlib.Path('tests/mutation_todos') / f"test_{safe_module}_{mutant_id}.py"
    rel_path.parent.mkdir(parents=True, exist_ok=True)
    destinations.append((str(rel_path), str(file_path), str(diff)))

    header = f"""# Auto-generated mutation TODO
# Module: {file_path}
# Mutant ID: {mutant_id}
"""
    if dry_run:
        body = f"""import pytest

pytestmark = pytest.mark.mutation_todo

def test_mutant_{mutant_id}_placeholder() -> None:
    pytest.skip('Proposed test for mutant {mutant_id}. Implement before enabling live writing.')
"""
        content = header + "\n" + body
    else:
        body = f"""import pytest

pytestmark = pytest.mark.mutation_todo

def test_mutant_{mutant_id}_todo() -> None:
    '''Mutation survivor scaffold.

    Summary: {summary}
    '''
    pytest.skip('TODO: add assertions that fail under mutant {mutant_id}.')
"""
        if diff:
            body += "\n# Mutmut diff:\n"
            body += "\n".join(f"# {line}" for line in diff.splitlines())
        content = header + "\n" + body

    rel_path.write_text(content, encoding='utf-8')

print("\n".join(path for path, _, _ in destinations))
PY
}

run_pytest_on_file() {
  local file="$1"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  echo "[mutants-orchestrator] pytest -q $file"
  if ! pytest -q "$file" >/dev/null; then
    echo "[mutants-orchestrator] pytest failed for $file; ensuring mutation_todo mark remains" >&2
  fi
}

should_stop() {
  TARGET_KILL="$TARGET_KILL" KILLRATE="$CURRENT_KILLRATE" SURV_CAP="$SURVIVORS_CAP" SURVIVED="$CURRENT_SURVIVED" python_eval <<'PY'
import os
target = float(os.environ['TARGET_KILL'])
killrate = float(os.environ['KILLRATE'])
cap = int(os.environ['SURV_CAP'])
survivors = int(os.environ['SURVIVED'])
if killrate >= target:
    print('kill-rate')
elif survivors <= cap:
    print('survivor-cap')
else:
    print('continue')
PY
}

iteration=1
while (( iteration <= MAX_ITER )); do
  echo "[mutants-orchestrator] === iteration $iteration ==="
  run_pytest_warm
  run_mutmut_cycle "iteration-$iteration-pre"

  decision=$(should_stop)
  if [[ "$decision" != "continue" ]]; then
    echo "[mutants-orchestrator] stopping criteria met (${decision})."
    break
  fi

  echo "[mutants-orchestrator] scaffolding TODO tests (dry-run=$DRY_RUN)"
  mapfile -t generated <<<"$(write_placeholders || true)"
  if ((${#generated[@]})) && [[ "$DRY_RUN" != "1" ]]; then
    for test_file in "${generated[@]}"; do
      [[ -n "$test_file" ]] || continue
      run_pytest_on_file "$test_file"
    done
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[mutants-orchestrator] DRY_RUN=1; skipping post-generation mutmut rerun"
  else
    run_mutmut_cycle "iteration-$iteration-post"
    decision=$(should_stop)
    if [[ "$decision" != "continue" ]]; then
      echo "[mutants-orchestrator] stopping criteria met after rerun (${decision})."
      break
    fi
  fi

  (( iteration++ ))
done

if (( iteration > MAX_ITER )); then
  echo "[mutants-orchestrator] reached maximum iterations ($MAX_ITER)"
fi

echo "[mutants-orchestrator] final status :: kill-rate=${CURRENT_KILLRATE} survived=${CURRENT_SURVIVED}"
