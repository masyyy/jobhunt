#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Applying derived Delta table migrations..."
python scripts/apply_delta_migrations.py

echo "Starting application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
