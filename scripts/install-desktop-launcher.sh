#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${XDG_DATA_HOME:-$HOME/.local/share}/applications/agenthop.desktop"
mkdir -p "$(dirname "$target")"
escape_exec_value() {
  local value="$1"
  if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "AgentHop paths must not contain newlines." >&2
    exit 1
  fi
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "$value"
}
launcher="$(escape_exec_value "$root/scripts/desktop.sh")"
icon="$root/frontend/public/assets/agenthop-mascot.png"
if [[ "$icon" == *$'\n'* || "$icon" == *$'\r'* || "$icon" == *' '* || "$icon" == *$'\t'* ]]; then
  echo "AgentHop icon paths must not contain whitespace or newlines." >&2
  exit 1
fi
printf '[Desktop Entry]\nType=Application\nName=AgentHop\nComment=Switch local AI coding accounts\nExec="%s"\nIcon=%s\nTerminal=false\nCategories=Development;\n' "$launcher" "$icon" > "$target"
echo "Installed $target. Your desktop environment may need a refresh before it appears."
