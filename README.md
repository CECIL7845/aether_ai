# Aether (provisional name)

A self-hosted AI workspace whose answers can be checked: chat, document intelligence, web research and data analysis across multiple AI providers.
See [docs/PLAN.md](docs/PLAN.md) for scope, architecture and phase status.

## Requirements

- Python 3.13 (managed by [uv](https://docs.astral.sh/uv/))
- Node 20+
- PostgreSQL 16+ with the `vector` extension available

## Local development

```bash
# Database: pgvector must be created by a superuser
createuser aether --pwprompt --createdb
createdb aether_dev -O aether
psql -d aether_dev -c "CREATE EXTENSION IF NOT EXISTS vector"
# Optional test template, so the test DB gets pgvector without superuser rights:
createdb aether_test_template -O aether
psql -d aether_test_template -c "CREATE EXTENSION IF NOT EXISTS vector"
psql -d postgres -c "ALTER DATABASE aether_test_template IS_TEMPLATE true"

# Backend
cd backend
cp .env.example .env          # then fill in the values
uv sync
uv run python manage.py migrate
uv run uvicorn config.asgi:application --port 8000

# Frontend (in another terminal); /api is proxied to :8000
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## Checks

```bash
cd backend && uv run pytest && uv run ruff check .
cd frontend && npm run build && npm run lint
```

## Tests

| Suite | Command | Notes |
|---|---|---|
| Backend unit/API | `cd backend && uv run pytest` | Uses a clearly labelled test-only provider; no network |
| Live provider smoke | `cd backend && RUN_LIVE_TESTS=1 uv run pytest apps/providers/tests/test_live.py` | Calls real APIs for configured keys |
| Frontend unit | `cd frontend && npm test` | Vitest + Testing Library |
| End-to-end | `cd frontend && npx playwright install chromium && npm run test:e2e` | Starts both servers; uses the real configured provider |
