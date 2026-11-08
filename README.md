# HookRelay

A reliable multi-tenant webhook delivery service. HookRelay receives events from your application, fans them out to registered endpoints, signs each request with HMAC-SHA256, and retries failed deliveries automatically.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running the Services](#running-the-services)
- [CLI — Tenant Management](#cli--tenant-management)
- [Scripts](#scripts)
- [API Reference](#api-reference)
- [Database Migrations](#database-migrations)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Project Structure](#project-structure)

---

## Architecture Overview

```
Publisher ──POST /v1/events──► API (FastAPI)
                                    │
                              writes Delivery rows
                                    │
                              Worker (polls DB) ──HTTP POST──► Endpoint URLs
```

Three independently deployable processes:

| Process | Description |
|---------|-------------|
| **api** | FastAPI service — tenant auth, endpoint CRUD, event ingestion |
| **worker** | Background process — claims pending deliveries, sends HTTP requests, records attempts |
| **postgres** | Persistent store for all data |
| **redis** | Reserved for future use (defined in compose) |

---

## Prerequisites

- Docker & Docker Compose **or** Python 3.11+ with a local Postgres instance
- `psql` / `curl` for manual testing (optional)

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd RWDS

# 2. Start all services
docker compose up --build

# 3. In another terminal, create your first tenant
python -m app.cli user@example.com my-app
# Output:
#   application_id : <uuid>
#   api_key        : hr_live_<prefix>_<secret>   ← save this, shown only once

# 4. Smoke test
curl http://localhost:8000/healthz          # → {"status":"ok"}
curl http://localhost:8000/readyz           # → {"status":"ok","database":"ok"}
```

---

## Configuration

All settings are read from a `.env` file (or real environment variables). Copy the table below to create your own `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | Async Postgres URL, e.g. `postgresql+asyncpg://user:pass@localhost/hookrelay` |
| `REDIS_URL` | — | Redis URL, e.g. `redis://localhost:6379/0` |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `ALLOW_INSECURE_ENDPOINTS` | `true` | Allow `http://` endpoint URLs (disable in prod) |
| `WORKER_CONCURRENCY` | `50` | Max parallel delivery tasks in the worker |
| `WORKER_POLL_SECONDS` | `1.0` | How often the worker polls for pending deliveries |
| `DELIVERY_TIMEOUT_SECONDS` | `10.0` | Per-request HTTP timeout for outbound webhooks |
| `LEASE_SECONDS` | `60` | How long a worker holds a delivery lock before it can be re-claimed |
| `RESPONSE_BODY_LIMIT` | `2048` | Max bytes captured from endpoint responses |

The `docker-compose.yml` pre-fills `DATABASE_URL` and `REDIS_URL` for local development.

---

## Running the Services

### Docker Compose (recommended)

```bash
# Start everything (api + worker + postgres + redis)
docker compose up

# Rebuild after code changes
docker compose up --build

# Run in background
docker compose up -d

# Stop
docker compose down

# Stop and wipe database volumes
docker compose down -v
```

The API is available at `http://localhost:8000`.

### Without Docker

```bash
# Install dependencies
pip install -e ".[dev]"

# Apply migrations (requires a running Postgres)
alembic upgrade head

# Start the API
uvicorn app.main:app --reload --port 8000

# Start the worker (separate terminal)
python -m app.worker
```

---

## CLI — Tenant Management

The CLI creates a new tenant (Account + Application + API key). Run it after the database is up.

```bash
python -m app.cli <email> <app_name>
```

**Example:**

```bash
python -m app.cli alice@example.com payments-service
```

**Output:**

```
application_id : 550e8400-e29b-41d4-a716-446655440000
api_key        : hr_live_a1b2c3d4_<base64-secret>
```

> The full API key is shown **once**. Store it securely — it cannot be recovered.

---

## Scripts

### `scripts/receiver.py` — Test Webhook Receiver

A lightweight HTTP server that listens on `127.0.0.1:9000`. Use it as a local endpoint target while developing or testing delivery.

```bash
python scripts/receiver.py
```

Available routes:

| Route | Behaviour |
|-------|-----------|
| `POST /` | Returns `200 OK` immediately, logs headers + body |
| `POST /slow` | Waits 30 seconds before responding (tests timeout handling) |
| `POST /fail` | Returns `500 Internal Server Error` (tests retry logic) |

**Typical workflow:**

```bash
# Terminal 1 — start the receiver
python scripts/receiver.py

# Terminal 2 — register it as an endpoint
curl -X POST http://localhost:8000/v1/endpoints \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://127.0.0.1:9000/", "event_types": ["*"]}'

# Terminal 2 — send an event
curl -X POST http://localhost:8000/v1/events \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "order.created", "payload": {"order_id": 42}}'

# Watch Terminal 1 for the delivered webhook
```

---

## API Reference

All endpoints require `Authorization: Bearer <api_key>` unless noted.

### Health

```
GET /healthz       → 200 {"status":"ok"}
GET /readyz        → 200 {"status":"ok","database":"ok"}
```

### Auth Check

```
GET /v1/whoami     → {"application_id":"...","key_prefix":"hr_live_..."}
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/endpoints` | Create a webhook endpoint |
| `GET` | `/v1/endpoints` | List endpoints (query: `limit`, `offset`) |
| `GET` | `/v1/endpoints/{id}` | Get one endpoint |
| `PATCH` | `/v1/endpoints/{id}` | Update url / description / event_types / status |
| `DELETE` | `/v1/endpoints/{id}` | Delete an endpoint |

**Create endpoint body:**

```json
{
  "url": "https://your-server.com/hooks",
  "description": "optional label",
  "event_types": ["order.created", "order.updated"]
}
```

Use `"event_types": ["*"]` to receive all events.

**Endpoint status values:** `active` | `paused` | `disabled`

The response to `POST /v1/endpoints` includes a `secret` field — this is the HMAC signing secret and is returned **only once**.

### Events

```
POST /v1/events
```

**Body:**

```json
{
  "event_type": "order.created",
  "payload": { "order_id": 42, "amount": 99.99 }
}
```

**Optional idempotency header:**

```
Idempotency-Key: <your-unique-key>
```

Returns `202 Accepted`. The worker delivers asynchronously.

**Limits:** Payload max 256 KB.

### Webhook Signature Verification

Each outbound webhook includes these headers:

| Header | Value |
|--------|-------|
| `Webhook-Id` | Event UUID |
| `Webhook-Timestamp` | Unix timestamp (seconds) |
| `Webhook-Signature` | `v1,<base64-hmac>` (space-separated if multiple secrets) |

Verify with HMAC-SHA256 over `{webhook_id}.{webhook_timestamp}.{raw_body}`.

---

## Database Migrations

Migrations are managed with Alembic.

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# Generate a new migration after model changes
alembic revision --autogenerate -m "description of change"

# Rollback one step
alembic downgrade -1
```

The API container runs `alembic upgrade head` automatically on startup.

---

## Testing

```bash
# Run all tests
pytest

# Quiet output
pytest -q

# Run a specific file
pytest tests/test_security.py
```

Tests require no running services — the test suite mocks infrastructure.

---

## Code Quality

The project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check . --fix

# Format code
ruff format .
```

Pre-commit hooks run ruff automatically on `git commit`. Install them once with:

```bash
pre-commit install
```

CI runs `ruff check` and `pytest` on every push and pull request.

---

## Project Structure

```
.
├── app/
│   ├── api/
│   │   ├── deps.py          # API key auth dependency
│   │   ├── endpoints.py     # Endpoint CRUD routes
│   │   ├── events.py        # Event publish route
│   │   ├── health.py        # /healthz and /readyz
│   │   ├── schemas.py       # Pydantic request/response models
│   │   └── whoami.py        # Auth introspection
│   ├── core/
│   │   ├── config.py        # Settings (pydantic-settings)
│   │   ├── security.py      # API key generation and verification
│   │   ├── signing.py       # HMAC-SHA256 webhook signing
│   │   └── urls.py          # Endpoint URL validation
│   ├── db/
│   │   ├── base.py          # SQLAlchemy declarative base
│   │   ├── models.py        # ORM models
│   │   └── session.py       # Async session factory
│   ├── cli.py               # Tenant creation CLI
│   ├── delivery.py          # Outbound HTTP delivery logic
│   ├── main.py              # FastAPI app factory
│   └── worker.py            # Async delivery worker
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 9e289531e67b_initial_schema.py
├── scripts/
│   └── receiver.py          # Local test webhook receiver
├── tests/
│   ├── test_health.py
│   └── test_security.py
├── docker-compose.yml
├── dockerfile
├── alembic.ini
└── pyproject.toml
```
