#!/bin/bash
set -euo pipefail

echo "[start] Waiting for Postgres at ${PG_HOST:-db}:${PG_PORT:-5432} ..."
for i in {1..60}; do
  if pg_isready -h "${PG_HOST:-db}" -p "${PG_PORT:-5432}" -U "${PG_USER:-securelink}" >/dev/null 2>&1; then
    echo "[start] Postgres is ready"
    break
  fi
  sleep 1
done

if [ -f "/app/database_migration.sql" ]; then
  echo "[start] Applying database migrations..."
  PGPASSWORD="${PG_PASSWORD:-}" psql \
    -h "${PG_HOST:-db}" -p "${PG_PORT:-5432}" \
    -U "${PG_USER:-securelink}" -d "${PG_DB:-securelink}" \
    -v ON_ERROR_STOP=1 \
    -f /app/database_migration.sql || true
fi

echo "[start] Launching Gunicorn (Flask app)"
gunicorn -w 4 -b 0.0.0.0:9000 App:app &

echo "[start] Launching Nginx"
nginx -g "daemon off;" &

echo "[start] Launching Telegram bot"
python3 simple_bot.py