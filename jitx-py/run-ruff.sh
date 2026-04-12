#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

mapfile -t projects < <(find . -mindepth 1 -maxdepth 1 -type d | while read -r project; do
  if [[ -f "$project/pyproject.toml" ]]; then
    printf "%s\n" "$project"
  fi
done | sort)

if [[ ${#projects[@]} -eq 0 ]]; then
  echo "No jitx-py child projects found"
  exit 0
fi

for project in "${projects[@]}"; do
  echo "==> Ruff: ${project#./}"
  (
    cd "$project"
    uv sync --extra dev
    uv run ruff check .
  )
done
