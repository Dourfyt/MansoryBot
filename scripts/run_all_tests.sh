#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
pip install -r requirements-dev.txt -q
pytest tests/ "$@"
cd "$ROOT/admin-app"
npm test
