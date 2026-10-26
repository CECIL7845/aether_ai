#!/bin/sh
# Runs the API server and the background task worker together (local development and E2E tests).
# Production should run them as separate services; see docs.
set -e
cd "$(dirname "$0")/.."
uv run python manage.py db_worker --interval 1 --no-startup-delay &
WORKER=$!
trap 'kill "$WORKER" 2>/dev/null || true' EXIT INT TERM
uv run uvicorn config.asgi:application --port "${PORT:-8000}"
