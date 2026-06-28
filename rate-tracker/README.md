# Rate Tracker

A production-style rate ingestion and tracking system: Django/DRF
backend, PostgreSQL, Redis caching, Celery + Celery Beat scheduling, and
a Next.js dashboard — built as a senior full-stack take-home-style
portfolio project.

See also: [`DECISIONS.md`](./DECISIONS.md) for the reasoning behind every
non-obvious architectural choice, and [`schema.md`](./schema.md) for the
full database design.

---

## Architecture

```
                         ┌─────────────┐
                         │  Next.js    │  (bonus dashboard)
                         │  Frontend   │
                         └──────┬──────┘
                                │ REST (JSON)
                                ▼
                      ┌───────────────────┐
                      │   Django + DRF    │
                      │   (web service)   │
                      └─────┬───────┬─────┘
                            │       │
                    ┌───────▼─┐   ┌─▼──────┐   ┌──────────────┐
                    │PostgreSQL│   │ Redis  │   │   Celery     │
                    │ (rates)  │   │ (cache)│   │Worker + Beat │
                    └──────────┘   └────────┘   └──────┬───────┘
                                                        │
                                                  reads Parquet
                                                        │
                                                  ┌─────▼──────┐
                                                  │ rates_seed │
                                                  │  .parquet  │
                                                  └────────────┘
```

All business logic (ingestion, query construction, cache invalidation)
lives in `backend/rates/services/` — views, the management command, and
Celery tasks are thin callers into the same service code. See
`DECISIONS.md` Section 1 for why.

---

## Project Structure

```
rate-tracker/
├── docker-compose.yml
├── .env.example
├── README.md / DECISIONS.md / schema.md
├── backend/
│   ├── config/                    # Django project settings, celery app, urls
│   ├── rates/
│   │   ├── models/                # Provider, RateType, Rate, RawIngestion
│   │   ├── services/               # ingestion, query, cache, normalization
│   │   ├── serializers/
│   │   ├── views/
│   │   ├── tasks.py                 # Celery tasks (thin)
│   │   ├── management/commands/seed_data.py
│   │   ├── authentication.py / permissions.py
│   │   ├── exceptions.py            # structured error responses
│   │   ├── logging_utils.py         # JSON structured logging
│   │   ├── middleware.py            # slow query logging
│   │   └── tests/
│   └── scripts/
│       ├── entrypoint.sh / validate_env.py
│       └── generate_seed_parquet.py
├── frontend/                       # Next.js dashboard (bonus)
└── data/
    └── rates_seed.parquet
```

---

## Setup

### Prerequisites
- Docker and Docker Compose

### Steps

```bash
cp .env.example .env
# Edit .env — at minimum set a real DJANGO_SECRET_KEY and INGESTION_API_TOKEN.
# Generate a secret key with:
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

docker-compose up --build
```

This starts: Postgres, Redis, the Django web service (migrations run
automatically on boot), a Celery worker, Celery Beat (scheduled
ingestion), and the Next.js frontend.

- API: http://localhost:8000/api/
- Health check: http://localhost:8000/health/
- Django admin: http://localhost:8000/admin/
- Frontend dashboard: http://localhost:3000

### Seeding data manually

The Parquet file at `data/rates_seed.parquet` is ingested automatically
by the Celery Beat schedule (default: hourly, configurable via
`INGESTION_SCHEDULE_MINUTES`). To trigger ingestion immediately instead
of waiting for the schedule:

```bash
docker-compose exec web python manage.py seed_data --file /app/data/rates_seed.parquet
```

Re-running this command is safe — ingestion is idempotent (see
`DECISIONS.md` Section 3).

### Creating an admin user (optional, for Django admin access)

```bash
docker-compose exec web python manage.py createsuperuser
```

---

## API Documentation

### `GET /api/rates/latest`

Latest rate per provider + rate type. No authentication required.

| Query param | Description |
|---|---|
| `provider` | Filter by provider name (case-insensitive) |
| `rate_type` | Filter by rate type code (case-insensitive) |

Response: `200 OK`, array of rate objects. Cached in Redis; see
`DECISIONS.md` Section 6 for invalidation strategy.

```bash
curl "http://localhost:8000/api/rates/latest?provider=HSBC"
```

### `GET /api/rates/history`

Paginated historical rates. No authentication required.

| Query param | Description |
|---|---|
| `provider` | Filter by provider name |
| `rate_type` | Filter by rate type code |
| `from` | Start date, `YYYY-MM-DD` |
| `to` | End date, `YYYY-MM-DD` |
| `limit` | Page size (capped server-side at 500 regardless of value requested) |
| `offset` | Pagination offset |

```bash
curl "http://localhost:8000/api/rates/history?provider=HSBC&from=2026-01-01&to=2026-01-31"
```

### `POST /api/rates/ingest`

Insert or update a single rate. **Requires Bearer token authentication.**

```bash
curl -X POST http://localhost:8000/api/rates/ingest \
  -H "Authorization: Bearer <INGESTION_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "HSBC",
    "rate_type": "MORTGAGE_30Y",
    "rate_value": "6.75",
    "effective_date": "2026-06-01"
  }'
```

Posting the same `provider` + `rate_type` + `effective_date` again
updates the existing record rather than creating a duplicate. Validation
errors return `400` with structured field-level detail; unexpected
server errors return a generic `500` with a correlation `error_id` —
never a raw stack trace.

---

## Testing

```bash
docker-compose exec web pytest
```

Coverage report is generated automatically (`pytest-cov`, configured in
`pytest.ini`). Test suite covers:

- Model constraints (uniqueness, decimal precision)
- Normalization utilities (provider casing, currency aliases)
- Ingestion service (idempotency, rejection handling, upsert-on-conflict)
- Query service (latest-rate grouping, history filtering)
- Serializers (validation rules, upsert behavior)
- API integration (latest/history/ingest endpoints, status codes)
- Authentication (Bearer scheme correctness, rejection paths)
- Cache invalidation (granular key targeting, event-driven correctness)
- Celery tasks (success/failure/retry paths, mocked ingestion)
- Management command (`seed_data` success and error paths)

---

## Code Quality

```bash
docker-compose exec web black .
docker-compose exec web ruff check .
docker-compose exec web isort .
docker-compose exec web mypy .
```

Configuration for all four lives in `backend/pyproject.toml`.

---

## Assumptions

- The natural key for a rate is `(provider, rate_type, effective_date)`;
  re-ingesting the same key upserts rather than rejects (see
  `DECISIONS.md` Section 3, based on patterns observed in the actual
  source data).
- `currency` defaults to `USD` when absent — the dataset is effectively
  single-currency today.
- A single static Bearer token is an acceptable simplification for the
  ingest endpoint's auth in this project's scope (see `DECISIONS.md`
  Section 8).

## Future Improvements

- Dedicated `GET /rates/changes` endpoint exposing 30-day rate deltas
  directly (the underlying query is already supported by `RateQueryService`).
- Per-client API keys with DRF throttling on the ingest endpoint.
- Materialized "latest rate" table if read latency becomes a bottleneck
  at much larger scale (see `schema.md`).
- Partition `Rate` by `effective_date` at significantly higher row counts.
- WebSocket or SSE push to the frontend instead of 60-second polling.
