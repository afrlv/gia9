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

URL="${IMESSAGE_RELAY_URL:-http://127.0.0.1:8765}"
if [[ "$URL" == *"host.docker.internal"* ]]; then
  URL="http://127.0.0.1:${IMESSAGE_RELAY_PORT:-8765}"
fi
TOKEN="${IMESSAGE_RELAY_TOKEN:-}"

if [[ -n "$TOKEN" ]]; then
  curl -fsS -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"Тест уведомления ГИА-9"}' \
    "$URL/notify"
else
  curl -fsS \
    -H "Content-Type: application/json" \
    -d '{"message":"Тест уведомления ГИА-9"}' \
    "$URL/notify"
fi

echo
echo "OK: сообщение отправлено"
