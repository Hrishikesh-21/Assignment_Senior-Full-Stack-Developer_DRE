#!/usr/bin/env bash
# Entrypoint for the Django/Celery containers.
#
# Why this exists rather than relying purely on docker-compose `depends_on`:
# depends_on only waits for the container process to *start*, not for
# Postgres to actually be ready to accept connections. Without this wait
# loop, Django would crash-loop on first `docker-compose up` while Postgres
# is still initializing its data directory.
set -e

echo "[entrypoint] Validating required environment variables..."
python /app/scripts/validate_env.py

echo "[entrypoint] Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
until python -c "
import socket, sys, os
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((os.environ['DB_HOST'], int(os.environ['DB_PORT'])))
    s.close()
except Exception:
    sys.exit(1)
"; do
  echo "[entrypoint] Postgres not ready yet, retrying in 1s..."
  sleep 1
done
echo "[entrypoint] PostgreSQL is reachable."

echo "[entrypoint] Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT}..."
until python -c "
import socket, sys, os
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((os.environ['REDIS_HOST'], int(os.environ['REDIS_PORT'])))
    s.close()
except Exception:
    sys.exit(1)
"; do
  echo "[entrypoint] Redis not ready yet, retrying in 1s..."
  sleep 1
done
echo "[entrypoint] Redis is reachable."

# Only the web service should run migrations, to avoid race conditions
# where celery worker/beat containers try to migrate concurrently with web.
if [ "$RUN_MIGRATIONS_ON_BOOT" = "true" ]; then
  echo "[entrypoint] Running migrations..."
  python manage.py migrate --noinput
fi

exec "$@"
