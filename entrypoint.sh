#!/bin/sh
set -e
mkdir -p /tmp/www
# Use the mounted ConfigMap if present, otherwise the data.json baked into the image
SRC="$DATA_FILE"; [ -f "$SRC" ] || SRC=/app/data.json
cd /app
python generate_dashboard.py "$SRC" /tmp/www/index.html
cd /tmp/www
exec python -m http.server "${PORT:-8080}" --bind 0.0.0.0
