#!/usr/bin/env bash
set -euo pipefail

# Wait for Postgres (compose healthcheck should have already done this, but belt-and-suspenders).
echo "[entrypoint] waiting for postgres at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}..."
until (exec 3<>/dev/tcp/${POSTGRES_HOST:-postgres}/${POSTGRES_PORT:-5432}) 2>/dev/null; do
  sleep 1
done
echo "[entrypoint] postgres is up"

# Run migrations (alembic added in Phase 3 — harmless no-op until then)
if [ -f "app/db/migrations/alembic.ini" ]; then
  echo "[entrypoint] running alembic upgrade head"
  uv run alembic -c app/db/migrations/alembic.ini upgrade head
fi

echo "[entrypoint] starting uvicorn"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
