#!/bin/bash
set -euo pipefail

echo "Recent audit artifacts include CSVs, JSON summaries, and snapshots. Review stages before committing."

git status -sb

read -r -p "Stage core source/docs for commit? [y/N] " ans
case "$ans" in
  [yY]*)
    git add \
      README.md \
      LICENSE \
      NOTICE \
      audit.md \
      upgrade.md \
      pyproject.toml \
      hashmap_cli.py \
      src \
      tests \
      docs \
      docker \
      Dockerfile \
      Dockerfile.dev \
      docker-compose.yml \
      Makefile
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
