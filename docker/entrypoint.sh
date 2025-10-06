#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  set -- serve
fi

cmd=("$@")

contains_flag() {
  local flag=$1
  shift
  for item in "$@"; do
    if [[ "$item" == "$flag" || "$item" == "$flag="* ]]; then
      return 0
    fi
  done
  return 1
}

if [[ "${cmd[0]}" == "serve" ]]; then
  extra=()
  if ! contains_flag "--host" "${cmd[@]}"; then
    extra+=("--host" "${ADHASH_METRICS_HOST:-0.0.0.0}")
  fi
  if ! contains_flag "--port" "${cmd[@]}"; then
    extra+=("--port" "${ADHASH_METRICS_PORT:-9090}")
  fi
  exec hashmap-cli "${cmd[@]}" "${extra[@]}"
fi

if [[ "${cmd[0]}" == "run-csv" ]]; then
  extra=()
  if [[ -n "${ADHASH_METRICS_PORT:-}" ]] && ! contains_flag "--metrics-port" "${cmd[@]}"; then
    extra+=("--metrics-port" "${ADHASH_METRICS_PORT}")
  fi
  if [[ -n "${ADHASH_METRICS_HOST:-}" ]] && ! contains_flag "--metrics-host" "${cmd[@]}"; then
    extra+=("--metrics-host" "${ADHASH_METRICS_HOST}")
  fi
  exec hashmap-cli "${cmd[@]}" "${extra[@]}"
fi

exec hashmap-cli "${cmd[@]}"
