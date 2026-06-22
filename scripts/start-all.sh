#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .data

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

wait_for_docker() {
  for _ in $(seq 1 30); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Docker не запущен. Откройте Docker Desktop." >&2
  return 1
}

start_relay() {
  if [[ "${IMESSAGE_ENABLED:-}" != "true" && "${IMESSAGE_ENABLED:-}" != "1" ]]; then
    echo "iMessage relay: пропущен (IMESSAGE_ENABLED не задан)"
    return 0
  fi

  if [[ -z "${IMESSAGE_TO:-}" ]]; then
    echo "iMessage relay: пропущен (IMESSAGE_TO не задан)" >&2
    return 1
  fi

  if [[ -f .data/relay.pid ]] && kill -0 "$(cat .data/relay.pid)" 2>/dev/null; then
    echo "iMessage relay: уже запущен (pid $(cat .data/relay.pid))"
    return 0
  fi

  nohup "$ROOT/scripts/run-imessage-relay.sh" >> .data/relay.log 2>&1 &
  echo $! > .data/relay.pid
  sleep 1

  if kill -0 "$(cat .data/relay.pid)" 2>/dev/null; then
    echo "iMessage relay: запущен (pid $(cat .data/relay.pid))"
  else
    echo "iMessage relay: не удалось запустить, см. .data/relay.log" >&2
    return 1
  fi
}

start_bot() {
  wait_for_docker
  docker compose up -d --build
  echo "GIA-9 monitor: запущен в Docker"
}

start_relay
start_bot

echo
echo "Готово. Логи:"
echo "  docker compose logs -f"
echo "  tail -f .data/relay.log"
