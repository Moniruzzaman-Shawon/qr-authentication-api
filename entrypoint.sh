#!/bin/sh
set -e

# Wait for the database, then apply migrations and seed the initial admin.
echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Seeding initial admin (if INITIAL_ADMIN_PASSWORD is set)..."
python manage.py seed_admin || true

exec "$@"
