#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# DEBUG: Print all environment variables to the log
echo "--- CHECKING ENVIRONMENT VARIABLES ---"
printenv
echo "--- Is DATABASE_URL set? ---"
echo "DATABASE_URL: $DATABASE_URL"
echo "------------------------------------"

# Run database migrations
echo "Running database migrations..."
# alembic upgrade head
echo "Migrations step skipped for initial deployment."
echo "Tables will be created by the application if they don't exist."
echo "Migrations completed."

# Start the application
echo "Starting application..."
uvicorn app:app --host 0.0.0.0 --port 8080
