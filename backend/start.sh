#!/bin/sh
set -e

# Run from this script's directory so alembic.ini and the app package resolve
# both in docker-compose (mounted at /app/backend) and the standalone image (/app/backend).
cd "$(dirname "$0")"

echo "Running database migrations..."
alembic upgrade head

echo "Seeding initial data..."
python -m app.seed

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
