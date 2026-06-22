#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${IMESSAGE_TO:-}" ]]; then
  echo "IMESSAGE_TO не задан в .env" >&2
  exit 1
fi

exec python3 "$ROOT/host/imessage_relay.py"
