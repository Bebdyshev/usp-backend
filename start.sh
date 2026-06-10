#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# DEBUG: Print all environment variables to the log
echo "--- CHECKING ENVIRONMENT VARIABLES ---"
printenv
echo "--- Is DATABASE_URL set? ---"
echo "DATABASE_URL: $DATABASE_URL"
echo "------------------------------------"

# Run database migrations (requires DATABASE_URL in Coolify / runtime env)
echo "Running database migrations..."
if [ -z "$DATABASE_URL" ]; then
  echo "WARNING: DATABASE_URL is not set; trying to load from .env..."
  # If DATABASE_URL is not in environment, try loading from .env
  if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo "Loaded DATABASE_URL from .env"
  fi
fi

# Use run_migration.py to ensure proper environment variable loading
if [ -f run_migration.py ]; then
  echo "Running migrations using run_migration.py..."
  python run_migration.py
else
  echo "run_migration.py not found, using alembic directly..."
  alembic upgrade head
fi
echo "Migrations step finished."

# Start the application
echo "Starting application..."
uvicorn app:app --host 0.0.0.0 --port 8080
