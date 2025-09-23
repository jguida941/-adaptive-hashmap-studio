#!/bin/bash
set -euo pipefail

echo "Recent audit artifacts include CSVs, JSON summaries, and snapshots. Review stages before committing."

git status -sb

read -r -p "Stage audit outputs for commit? [y/N] " ans
case "$ans" in
  [yY]*)
    git add audit.md README.md hashmap_cli.py perf_*.json demo_perf.json state.pkl.gz rh_*.pkl.gz demo*.pkl.gz chain.pkl.gz w_*.csv demo.csv
    git status -sb
    read -r -p "Commit now? [y/N] " commit_ans
    if [[ "$commit_ans" =~ ^[yY] ]]; then
      read -r -p "Commit message: " msg
      git commit -m "$msg"
    else
      echo "Commit skipped."
    fi
    ;;
  *)
    echo "Nothing staged."
    ;;
esac
