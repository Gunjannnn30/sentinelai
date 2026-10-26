#!/usr/bin/env bash
# Apply database migrations (production schema path).
#   ./scripts/migrate.sh            # alembic upgrade head
#   ./scripts/migrate.sh current    # show current revision
# Env: SENTINEL_DATABASE_URL must point at the target database.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

export SENTINEL_APP_ENV="${SENTINEL_APP_ENV:-development}"
export SENTINEL_AUTH_SECRET="${SENTINEL_AUTH_SECRET:-migrate-placeholder}"

PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="python3"

ACTION="${1:-upgrade head}"
exec "$PY" -m alembic $ACTION
