#!/usr/bin/env bash
set -euo pipefail

ART="${1:-.artifacts}"
COV_XML="${ART}/coverage.xml"
JUNIT_XML="${ART}/junit.xml"
SEMGREP_SARIF="${ART}/semgrep.sarif"
MUT_RESULTS="${ART}/mutation_results.txt"
GRYPE_JSON="${ART}/grype.json"
TRIVY_JSON="${ART}/trivy.json"
PIPA_JSON="${ART}/pip-audit.json"
SUMMARY_MD="${ART}/summary.md"
METRICS_JSON="${ART}/metrics.json"

mkdir -p "$ART"

COV_MIN=${COV_MIN:-90.0}
MUT_MIN=${MUT_MIN:-85.0}
COV_DELTA_WARN=${COV_DELTA_WARN:--0.5}

profile="${PIPELINE_MODE:-fast}"
runtime_min="${PIPELINE_MINUTES:-0}"

cov_pct="0.0"
if [ -f "$COV_XML" ]; then
  rate=$(grep -Eo 'branch-rate="([0-9.]+)"' "$COV_XML" | head -n1 | sed -E 's/.*="([0-9.]+)"/\1/' || true)
  if [ -n "${rate:-}" ]; then
    cov_pct=$(awk -v r="$rate" 'BEGIN{printf("%.1f", r*100.0)}')
  fi
fi
cov_delta="${COV_DELTA_PCT:-0.0}"

mut_kill_pct="0.0"
mut_survivors="0"
if [ -f "$MUT_RESULTS" ]; then
  survived=$(grep -Eci '(^| )survived( |$)' "$MUT_RESULTS" || true)
  killed=$(grep -Eci '(^| )killed( |$)' "$MUT_RESULTS" || true)
  total=$(( survived + killed ))
  mut_survivors="$survived"
  if [ "$total" -gt 0 ]; then
    mut_kill_pct=$(awk -v k="$killed" -v t="$total" 'BEGIN{printf("%.1f", (k*100.0)/t)}')
  fi
fi

semgrep_high="0"
if [ -f "$SEMGREP_SARIF" ]; then
  semgrep_high=$(grep -Eoc '"level"[[:space:]]*:[[:space:]]*"(error|critical)"' "$SEMGREP_SARIF" || true)
fi

bandit_high="${BANDIT_HIGH:-0}"

vuln_high=0
if [ -f "$GRYPE_JSON" ]; then
  vuln_high=$((vuln_high + $(grep -Eoc '"severity"[[:space:]]*:[[:space:]]*"(High|Critical)"' "$GRYPE_JSON" || true)))
fi
if [ -f "$TRIVY_JSON" ]; then
  vuln_high=$((vuln_high + $(grep -Eoc '"Severity"[[:space:]]*:[[:space:]]*"(HIGH|CRITICAL)"' "$TRIVY_JSON" || true)))
fi
if [ -f "$PIPA_JSON" ]; then
  pip_audit_high=$(
    python3 - <<'PY' "$PIPA_JSON"
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
if isinstance(data, dict):
    entries = data.get("dependencies", [])
else:
    entries = data
count = 0
for dep in entries:
    for vuln in dep.get("vulns", []):
        severity = vuln.get("severity")
        if severity and severity.upper() in {"HIGH", "CRITICAL"}:
            count += 1
print(count)
PY
  )
  vuln_high=$((vuln_high + pip_audit_high))
fi

license_violations="${LICENSE_VIOLATIONS:-0}"

slow_test="n/a"
if [ -f "$JUNIT_XML" ]; then
  slow_test=$(awk '
    match($0, /<testcase[^>]*name="([^"]+)"[^>]*time="([0-9.]+)"/, a) {
      name=a[1]; t=a[2];
      if (t>max) {max=t; slow=name " (" t " s)";}
    }
    END{ if (slow!="") print slow; else print "n/a" }
  ' "$JUNIT_XML")
fi

red=0
yellow=0
awk "BEGIN{exit ($cov_pct < $COV_MIN)}" || red=1
awk "BEGIN{exit ($mut_kill_pct < $MUT_MIN)}" || red=1
[ "$mut_survivors" -gt 0 ] && red=1
[ "$semgrep_high" -gt 0 ] && red=1
[ "$bandit_high" -gt 0 ] && red=1
[ "$vuln_high" -gt 0 ] && red=1
[ "$license_violations" -gt 0 ] && red=1
awk "BEGIN{exit ($cov_delta < $COV_DELTA_WARN)}" || yellow=1

status="✅"
[ $yellow -eq 1 ] && status="⚠️"
[ $red -eq 1 ] && status="❌"

cov_ok=$(awk "BEGIN{print ($cov_pct >= $COV_MIN)}")
mut_ok=$(awk "BEGIN{print ($mut_kill_pct >= $MUT_MIN)}")
cov_delta_ok=$(awk "BEGIN{print ($cov_delta >= $COV_DELTA_WARN)}")

cat > "$SUMMARY_MD" <<EOF
### $status Pipeline Summary (${profile} profile)

| Metric                       | Result   | Threshold | Status |
|------------------------------|---------:|----------:|:------:|
| Branch Coverage              | ${cov_pct}% | ≥ ${COV_MIN}% | $([ "$cov_ok" -eq 1 ] && echo "✅" || echo "❌") |
| Coverage Δ vs base           | $(printf "%+.1f" "$cov_delta")% | ≥ ${COV_DELTA_WARN}% | $([ "$cov_delta_ok" -eq 1 ] && echo "✅" || echo "⚠️") |
| Mutation Kill Ratio          | ${mut_kill_pct}% | ≥ ${MUT_MIN}% | $([ "$mut_ok" -eq 1 ] && echo "✅" || echo "❌") |
| Mutation Survivors           | ${mut_survivors} | 0 | $([ "$mut_survivors" -eq 0 ] && echo "✅" || echo "❌") |
| Semgrep (HIGH/CRIT)          | ${semgrep_high} | 0 | $([ "$semgrep_high" -eq 0 ] && echo "✅" || echo "❌") |
| Bandit (HIGH)                | ${bandit_high} | 0 | $([ "$bandit_high" -eq 0 ] && echo "✅" || echo "❌") |
| Vulnerabilities (HIGH/CRIT)  | ${vuln_high} | 0 | $([ "$vuln_high" -eq 0 ] && echo "✅" || echo "❌") |
| License Violations           | ${license_violations} | 0 | $([ "$license_violations" -eq 0 ] && echo "✅" || echo "❌") |
| Slowest Test                 | ${slow_test} | — | ℹ️ |
| Total Runtime                | ${runtime_min} min | — | ℹ️ |

Artifacts: coverage.xml/html, junit.xml, mutation_results.txt, semgrep.sarif, sbom.cdx.json, grype.json, pip-audit.json in \`${ART}\`.
EOF

ts="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
cat > "$METRICS_JSON" <<EOF
{
  "timestamp_utc": "$ts",
  "profile": "$profile",
  "coverage_branch_pct": $(printf "%.1f" "$cov_pct"),
  "coverage_delta_pct": $(printf "%.1f" "$cov_delta"),
  "mutation_kill_ratio_pct": $(printf "%.1f" "$mut_kill_pct"),
  "mutation_survivors": $mut_survivors,
  "semgrep_high": $semgrep_high,
  "bandit_high": $bandit_high,
  "vuln_high": $vuln_high,
  "license_violations": $license_violations,
  "runtime_minutes": $(printf "%.1f" "$runtime_min")
}
EOF

echo "Wrote $SUMMARY_MD and $METRICS_JSON"
