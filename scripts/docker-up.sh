#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

for _ in $(seq 1 60); do
  if docker info >/dev/null 2>&1; then
    docker compose up -d
    exit 0
  fi
  sleep 5
done

echo "Docker так и не стал доступен" >&2
exit 1
