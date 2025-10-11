#!/usr/bin/env bash
set -euo pipefail

XML="${1:-.artifacts/coverage-aggregate.xml}"
OUT="${2:-.artifacts/coverage-badge.svg}"

pct="0"
if [ -f "$XML" ]; then
  rate=$(grep -Eo 'line-rate="([0-9.]+)"' "$XML" | head -n1 | sed -E 's/.*="([0-9.]+)"/\1/' || true)
  if [ -n "${rate:-}" ]; then
    pct=$(awk -v r="$rate" 'BEGIN{printf("%d", int(r*100))}')
  fi
fi

color="#e05d44"
if   [ "$pct" -ge 90 ]; then color="#4c1"
elif [ "$pct" -ge 80 ]; then color="#a4c639"
elif [ "$pct" -ge 70 ]; then color="#dfb317"
elif [ "$pct" -ge 60 ]; then color="#fe7d37"
fi

out_dir="$(dirname "$OUT")"
mkdir -p "$out_dir"

cat > "$OUT" <<SVG
<svg xmlns="http://www.w3.org/2000/svg" width="150" height="20" role="img" aria-label="coverage: ${pct}%">
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <mask id="m"><rect width="150" height="20" rx="3" fill="#fff"/></mask>
  <g mask="url(#m)">
    <rect width="80" height="20" fill="#555"/>
    <rect x="80" width="70" height="20" fill="#4c1"/>
    <rect width="150" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="40" y="15">coverage</text>
    <text x="115" y="15">${pct}%</text>
  </g>
</svg>
SVG

sed -i.bak "s|fill=\"#4c1\"|fill=\"${color}\"|" "$OUT" && rm -f "$OUT.bak"
echo "Badge -> $OUT"
