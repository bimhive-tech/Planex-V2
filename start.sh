#!/usr/bin/env bash
# Container entrypoint: migrate, then run Django (internal :8000) + Next ($PORT).
set -e

cd /app/backend

echo "→ Running migrations…"
python manage.py migrate --noinput

# Seed the platform admin on first boot (idempotent).
if [ "${SEED_PLATFORM:-true}" = "true" ]; then
  echo "→ Seeding platform admin…"
  python manage.py seed_platform || true
fi

echo "→ Starting Django (gunicorn) on :8000…"
# --timeout 300: large reports (detailed grid over tens of thousands of activities)
# render well past the 30s default. The front-door PDF route handler fetches with
# the same headroom, bypassing Next's rewrite proxy which resets long responses.
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers "${WEB_CONCURRENCY:-2}" --timeout 300 &

cd /app/frontend
export PORT="${PORT:-3000}"
export HOSTNAME="0.0.0.0"
export BACKEND_INTERNAL_URL="http://127.0.0.1:8000"
echo "→ Starting Next.js on :${PORT}…"
exec node server.js
