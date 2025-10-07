#!/usr/bin/env bash
# Mutation testing triage helper.
# Fetch the latest GitHub Actions artifact (if available), regenerate a
# survivors report locally, and optionally publish the results.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (env overrides available)
# ---------------------------------------------------------------------------
WORKFLOW="${WORKFLOW:-mutmut.yml}"
ART_NAME="${ART_NAME:-mutmut-results}"
OUTDIR="${OUTDIR:-.mutmut-ci}"
TOPN="${TOPN:-25}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REPORT_DEST="${REPORT_DEST:-file}" # file|issue|pr|stdout|none
LOCAL_ONLY="${MUTANTS_LOCAL_ONLY:-0}" # set to 1 to skip GH artifact download
FETCH_ARTIFACT="${FETCH_ARTIFACT:-auto}" # auto|1|0 (auto uses gh presence and LOCAL_ONLY)
SKIP_MUTMUT_INSTALL="${SKIP_MUTMUT_INSTALL:-0}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { printf '[mutants] %s\n' "$*" >&2; }
warn() { printf '[mutants] warning: %s\n' "$*" >&2; }
fail() { printf '[mutants] error: %s\n' "$*" >&2; exit 1; }

have_cmd() { command -v "$1" >/dev/null 2>&1; }

resolve_python() {
  local candidate
  for candidate in "$PYTHON_BIN" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------
if [[ -n "${CI:-}" && "${DOCS_BUILD:-}" == "1" ]]; then
  log "Docs build detected; skipping mutation triage."
  exit 0
fi

mkdir -p "$OUTDIR"

GH_AVAILABLE=0
if have_cmd gh; then
  GH_AVAILABLE=1
fi

if [[ "$FETCH_ARTIFACT" == "auto" ]]; then
  if [[ "$LOCAL_ONLY" == "1" || $GH_AVAILABLE -eq 0 ]]; then
    FETCH_ARTIFACT=0
  else
    FETCH_ARTIFACT=1
  fi
fi

if [[ "$FETCH_ARTIFACT" == "1" && $GH_AVAILABLE -eq 0 ]]; then
  warn "GitHub CLI not available; switching to local-only mode."
  FETCH_ARTIFACT=0
fi

PYTHON_BIN_RESOLVED="$(resolve_python || true)"
if [[ -z "$PYTHON_BIN_RESOLVED" ]]; then
  fail "no usable Python interpreter found (expected '$PYTHON_BIN' or python3/python)."
fi
PIP_BIN="$PYTHON_BIN_RESOLVED -m pip"

# Required Unix tools
for tool in awk grep sed; do
  have_cmd "$tool" || fail "required command '$tool' not found on PATH."
done

# ---------------------------------------------------------------------------
# Fetch latest workflow artifact (optional)
# ---------------------------------------------------------------------------
RUN_ID=""
ART_SUMMARY=""
if [[ "$FETCH_ARTIFACT" == "1" ]]; then
  log "Looking up latest '$WORKFLOW' workflow run…"
  RUN_ID="$(gh run list --workflow "$WORKFLOW" --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || true)"
  if [[ -z "$RUN_ID" ]]; then
    warn "no workflow runs found for '$WORKFLOW'; continuing with local data."
  else
    log "Downloading artifact '$ART_NAME' from run $RUN_ID…"
    if gh run download "$RUN_ID" -n "$ART_NAME" -D "$OUTDIR"; then
      ART_SUMMARY="$OUTDIR/mutmut_results.txt"
      if [[ -f "$ART_SUMMARY" ]]; then
        log "Saved CI summary to $ART_SUMMARY"
      else
        warn "artifact '$ART_NAME' missing mutmut_results.txt (continuing)"
      fi
    else
      warn "failed to download artifact '$ART_NAME' (run $RUN_ID); continuing locally."
      RUN_ID=""
    fi
  fi
else
  log "Skipping artifact download (local-only mode)."
fi

# ---------------------------------------------------------------------------
# Ensure mutmut tooling is available
# ---------------------------------------------------------------------------
if [[ "$SKIP_MUTMUT_INSTALL" == "1" ]]; then
  log "Skipping mutmut installation (SKIP_MUTMUT_INSTALL=1)."
else
  log "Ensuring mutmut + pytest are installed…"
  $PIP_BIN install -q --upgrade pip >/dev/null
  $PIP_BIN install -q mutmut pytest >/dev/null
fi

SUMMARY_PATH="$OUTDIR/summary.txt"
SURVIVORS_RAW="$OUTDIR/survivors.raw"
log "Collecting mutmut results…"
if ! mutmut results >"$SUMMARY_PATH" 2>"$OUTDIR/mutmut_results.err"; then
  warn "mutmut results returned non-zero status; see $OUTDIR/mutmut_results.err"
fi
awk '/Survived/{capture=1;next} capture && NF{print}' "$SUMMARY_PATH" >"$SURVIVORS_RAW" || true

ids="$(mutmut results | awk '/Survived/{capture=1;next} capture && $1 ~ /^[0-9]+$/ {print $1}')"
survivor_count="$(wc -w <<<"$ids" | awk '{print $1}')"
log "Surviving mutants: ${survivor_count:-0}"
scoreboard_line="$(grep -m1 '🎉' "$SUMMARY_PATH" || true)"
if [[ -n "$scoreboard_line" ]]; then
  log "Scoreboard: $scoreboard_line"
fi

# ---------------------------------------------------------------------------
# Generate Markdown report
# ---------------------------------------------------------------------------
REPORT="$OUTDIR/survivors_report.md"
: >"$REPORT"
{
  echo "# Mutation Survivors (Top $TOPN)"
  echo
  printf -- "- Workflow: \`%s\`\n" "$WORKFLOW"
  if [[ -n "$RUN_ID" ]]; then
    printf -- "- Run: %s\n" "$RUN_ID"
  fi
  echo "- Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  if [[ -f "$ART_SUMMARY" ]]; then
    echo
    echo "## CI Summary"
    echo '```'
    cat "$ART_SUMMARY"
    echo '```'
  fi
} >>"$REPORT"

processed_ids=()
if [[ -z "$ids" ]]; then
  {
    echo
    echo "No surviving mutants were reported. 🎉"
  } >>"$REPORT"
else
  {
    echo
    echo "## Survivor Details"
    echo
  } >>"$REPORT"
  i=0
  for id in $ids; do
    ((i++))
    if (( i > TOPN )); then
      break
    fi
    processed_ids+=("$id")
    {
      echo "### Survivor $id"
      echo
      diff_file="$OUTDIR/survivor_${id}.diff"
      if mutmut show "$id" >"$diff_file"; then
        cat "$diff_file" >>"$REPORT"
      else
        echo "_Unable to render diff for survivor $id (mutmut show failed)._"
        rm -f "$diff_file"
      fi
      echo
    } >>"$REPORT"
  done
  if (( survivor_count > TOPN )); then
    echo "_Additional survivors omitted (set TOPN to a larger value to include more)._"
    echo
  fi >>"$REPORT"
fi

log "Wrote report to $REPORT"

if ((${#processed_ids[@]})); then
  TOP_IDS="$(printf '%s\n' "${processed_ids[@]}" | paste -sd' ' -)"
else
  TOP_IDS=""
fi

JSON_PATH="$OUTDIR/survivors_report.json"
STEP_SUMMARY_PATH="$OUTDIR/github_step_summary.md"
export SUMMARY_PATH SURVIVORS_RAW OUTDIR JSON_PATH STEP_SUMMARY_PATH WORKFLOW RUN_ID TOPN TOP_IDS
export SCOREBOARD_LINE="$scoreboard_line"
python - <<'PY'
import json
import os
import re
from datetime import datetime, timezone

summary_path = os.environ.get("SUMMARY_PATH")
survivors_raw = os.environ.get("SURVIVORS_RAW")
outdir = os.environ.get("OUTDIR", ".mutmut-ci")
json_path = os.environ.get("JSON_PATH", os.path.join(outdir, "survivors_report.json"))
step_summary_path = os.environ.get("STEP_SUMMARY_PATH", os.path.join(outdir, "github_step_summary.md"))
scoreboard_line = os.environ.get("SCOREBOARD_LINE", "")
workflow = os.environ.get("WORKFLOW")
run_id = os.environ.get("RUN_ID") or None
topn = int(os.environ.get("TOPN", "0") or 0)
top_ids = [s for s in os.environ.get("TOP_IDS", "").split() if s]

scoreboard = None
if scoreboard_line:
    executed = total = None
    m = re.search(r'(\d+)\s*/\s*(\d+)', scoreboard_line)
    if m:
        executed, total = int(m.group(1)), int(m.group(2))

    def grab(symbol: str) -> int | None:
        m = re.search(re.escape(symbol) + r"\s+(\d+)", scoreboard_line)
        return int(m.group(1)) if m else None

    scoreboard = {
        "executed": executed,
        "total": total,
        "killed": grab("🎉"),
        "survived": grab("🫥"),
        "timeout": grab("⏰"),
        "incompetent": grab("🤔"),
        "suspicious": grab("🙁"),
        "muted": grab("🔇"),
        "raw": scoreboard_line.strip(),
    }

survivor_entries = []
if survivors_raw and os.path.exists(survivors_raw):
    with open(survivors_raw, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split(None, 1)
            if not parts:
                continue
            try:
                mut_id = int(parts[0])
            except ValueError:
                continue
            summary = parts[1] if len(parts) > 1 else ""
            path = None
            line_no = None
            match = re.search(r'([A-Za-z0-9_./-]+\.py)(?::(\d+))?', summary)
            if match:
                path = match.group(1)
                if match.group(2):
                    line_no = int(match.group(2))
            diff_path = os.path.join(outdir, f"survivor_{mut_id}.diff")
            diff_text = None
            if os.path.exists(diff_path):
                diff_text = open(diff_path, "r", encoding="utf-8", errors="ignore").read()
            survivor_entries.append(
                {
                    "id": mut_id,
                    "summary": summary,
                    "file": path,
                    "line": line_no,
                    "diff": diff_text,
                }
            )

timestamp = datetime.now(tz=timezone.utc).isoformat()
data = {
    "schema_version": 1,
    "generated_at": timestamp,
    "workflow": workflow,
    "run_id": run_id,
    "top_limit": topn,
    "top_ids": top_ids,
    "scoreboard": scoreboard,
    "survivor_count": len(survivor_entries),
    "survivors": survivor_entries,
}

with open(json_path, "w", encoding="utf-8") as fp:
    json.dump(data, fp, indent=2)

summary_lines = []
if scoreboard:
    summary_lines.append(f"## Mutation Summary")
    summary_lines.append("")
    executed = scoreboard.get("executed")
    total = scoreboard.get("total")
    if executed is not None and total is not None:
        summary_lines.append(f"- Coverage: {executed}/{total} mutants evaluated")
    summary_lines.append(
        "- 🎉 killed: {killed}  🫥 survived: {survived}  ⏰ timeout: {timeout}  🙁 suspicious: {suspicious}".format(
            killed=scoreboard.get("killed", "n/a"),
            survived=scoreboard.get("survived", "n/a"),
            timeout=scoreboard.get("timeout", "n/a"),
            suspicious=scoreboard.get("suspicious", "n/a"),
        )
    )
if survivor_entries:
    top_preview = ", ".join(str(entry["id"]) for entry in survivor_entries[: min(5, len(survivor_entries))])
    summary_lines.append(f"- Survivors recorded: {len(survivor_entries)} (top IDs: {top_preview})")
else:
    summary_lines.append("- Survivors recorded: 0 🎉")

with open(step_summary_path, "w", encoding="utf-8") as fp:
    fp.write("\n".join(summary_lines) + "\n")
PY

log "Wrote JSON summary to $JSON_PATH"
STEP_SUMMARY_PATH="$STEP_SUMMARY_PATH"

# ---------------------------------------------------------------------------
# Publish report (depending on REPORT_DEST)
# ---------------------------------------------------------------------------
case "$REPORT_DEST" in
  issue)
    if [[ "$GH_AVAILABLE" -eq 0 ]]; then
      warn "REPORT_DEST=issue but gh not available; skipping."
    else
      title="Mutation survivors report${RUN_ID:+ ($RUN_ID)}"
      existing="$(gh issue list --search "$title in:title" --json number -q '.[0].number' 2>/dev/null || true)"
      if [[ -n "$existing" ]]; then
        log "Appending report to existing issue #$existing"
        gh issue comment "$existing" -F "$REPORT" >/dev/null || warn "failed to comment on issue #$existing"
      else
        log "Creating tracking issue: $title"
        gh issue create --title "$title" --body-file "$REPORT" --label testing --label mutation-testing >/dev/null || \
          warn "failed to create GitHub issue (continuing)"
      fi
    fi
    ;;
  pr)
    if [[ "$GH_AVAILABLE" -eq 0 ]]; then
      warn "REPORT_DEST=pr but gh not available; skipping."
    else
      log "Posting survivors report as PR comment (if PR detected)…"
      gh pr comment -F "$REPORT" >/dev/null || warn "failed to post PR comment (perhaps not in PR context)"
    fi
    ;;
  stdout)
    log "Emitting report to stdout:"
    cat "$REPORT"
    ;;
  none)
    log "Report generation complete (no publish requested)."
    ;;
  file)
    log "Report available at $REPORT"
    ;;
  *)
    warn "Unknown REPORT_DEST='$REPORT_DEST'; defaulting to file output."
    ;;
esac

# ---------------------------------------------------------------------------
# Generate TODO test stubs
# ---------------------------------------------------------------------------
if [[ -n "$ids" ]]; then
  mkdir -p tests/mutation_todos
  log "Creating placeholder mutation TODO tests…"
  grep -E '^File: ' "$REPORT" | awk '{print $2}' | sort -u | while read -r path; do
    [[ -z "$path" ]] && continue
    if [[ "$path" != src/* ]]; then
      continue
    fi
    mod="${path#src/}"
    base="$(echo "$mod" | tr '/' '_' | sed 's/\.py$//')"
    tfile="tests/mutation_todos/test_${base}_mutation_todo.py"
    if [[ -f "$tfile" ]]; then
      continue
    fi
    cat >"$tfile" <<'PY'
import pytest

pytestmark = pytest.mark.mutation_todo


def test_kill_mutants_placeholder() -> None:
    pytest.skip(
        "TODO: Inspect mutmut diffs for this module and replace with concrete "
        "assertions that kill the surviving mutant(s)."
    )
PY
    log "Added $tfile"
  done
else
  log "No survivors; skipping TODO test generation."
fi

log "Mutation triage complete."
