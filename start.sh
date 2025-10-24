#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
echo "Running database migrations..."
alembic upgrade head
echo "Migrations completed."

# Start the application
echo "Starting application..."
uvicorn app:app --host 0.0.0.0 --port 8080
