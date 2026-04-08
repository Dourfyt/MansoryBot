#!/usr/bin/env bash
# Запуск pytest и vitest в контейнерах (PostgreSQL должен быть доступен по DATABASE_URL с хостом postgres).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker compose up -d postgres
docker compose --profile test run --rm test-python
docker compose --profile test run --rm test-admin
