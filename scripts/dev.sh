#!/usr/bin/env bash
set -euo pipefail

python_bin="${PYTHON:-python3}"
npm_bin="${NPM:-npm}"

"$python_bin" -m agenthop --reload --port 8000 &
backend_pid=$!

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd frontend
"$npm_bin" run dev
