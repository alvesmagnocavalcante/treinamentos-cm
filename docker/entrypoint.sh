#!/bin/sh
set -eu

python manage.py migrate --no-input
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-10000}" \
    --workers 1 --threads 4 --timeout 180 \
    --access-logfile - --error-logfile -
