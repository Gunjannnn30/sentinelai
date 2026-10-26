#!/usr/bin/env bash
# Boot SentinelAI for local development (SQLite + in-process rate limiter).
#   ./scripts/dev.sh
#   backend  http://127.0.0.1:8123  (docs at /docs)
#   frontend http://127.0.0.1:3000
#
# The frontend is started by the process that already runs it (the agent, or
# you); this script only guarantees the backend is up with sane defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

# Local-dev defaults (SENTINEL_ prefix is mandatory — config reads only these).
export SENTINEL_APP_ENV="${SENTINEL_APP_ENV:-development}"
export SENTINEL_AUTH_SECRET="${SENTINEL_AUTH_SECRET:-dev-only-local-secret-0f2c9a4e7b1d}"
export SENTINEL_DATABASE_URL="${SENTINEL_DATABASE_URL:-sqlite:///./data/sentinelai.db}"
export SENTINEL_SESSION_COOKIE_SECURE="${SENTINEL_SESSION_COOKIE_SECURE:-false}"
export SENTINEL_SEED_DEMO_DATA="${SENTINEL_SEED_DEMO_DATA:-true}"

PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="python3"   # fallback for non-Windows checkouts

mkdir -p data
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8123 --reload
