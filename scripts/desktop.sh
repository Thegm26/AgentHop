#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${AGENTHOP_BACKEND_PYTHON:-$root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "Create the project virtual environment first: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi
dist_index="$root/frontend/dist/index.html"
needs_build=false
if [[ ! -f "$dist_index" ]]; then
  needs_build=true
elif find "$root/frontend/src" "$root/frontend/public" -type f -newer "$dist_index" -print -quit | grep -q .; then
  needs_build=true
else
  for input in index.html package.json package-lock.json vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json eslint.config.js; do
    if [[ "$root/frontend/$input" -nt "$dist_index" ]]; then
      needs_build=true
      break
    fi
  done
fi

if [[ "$needs_build" == true ]]; then
  (cd "$root/frontend" && npm run build)
fi
AGENTHOP_BACKEND_PYTHON="$python_bin" AGENTHOP_PROJECT_ROOT="$root" \
  exec /usr/bin/python3 "$root/backend/agenthop/desktop.py"
