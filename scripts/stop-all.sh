#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .data/relay.pid ]]; then
  pid="$(cat .data/relay.pid)"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "iMessage relay: остановлен (pid $pid)"
  fi
  rm -f .data/relay.pid
fi

docker compose down
echo "GIA-9 monitor: остановлен"
