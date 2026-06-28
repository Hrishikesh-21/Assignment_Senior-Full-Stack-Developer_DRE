# Architecture Decisions

This document explains the *why* behind every non-obvious choice in
this project. Where multiple reasonable approaches existed, the
alternative considered and the reason it was not chosen are recorded.

---

## 1. Service Layer Architecture

**Decision:** All business logic lives in `rates/services/`. Views,
the management command, and Celery tasks are thin callers.

**Why:** the same ingestion logic needs to run from three entry points
(manual `seed_data` command, scheduled Celery task, and conceptually
the single-record `POST /rates/ingest` path, which shares validation
rules via the serializer calling into normalization helpers). Putting
the logic in any one of those three places would mean either duplicating
it (drift risk) or having one caller awkwardly invoke another (e.g. the
Celery task calling the management command as a subprocess, which is
fragile and hard to test). A pure service module, with no Django
request/response or CLI concerns, is callable from anywhere and is
independently unit-testable.

---

## 2. Real Source Data Discovery Changed the Design

The spec described required fields as `provider_name`, `rate_type`,
`rate_value`, `effective_date`, `ingestion_timestamp`. When the actual
`rates_seed.parquet` file was inspected, several differences emerged:

| Spec said | Actual file has |
|---|---|
| `provider_name` | `provider` |
| `ingestion_timestamp` | `ingestion_ts` |
| Snappy compression | ZSTD compression |
| (not mentioned) | `source_url`, `raw_response_id`, `currency` columns also present |

**Decision:** built the ingestion service against the actual file's
schema, kept the three extra columns as optional fields on `Rate`
rather than discarding them, and used pyarrow's compression-agnostic
reader (compression codec is stored in the Parquet file's metadata and
handled transparently — no special-casing needed for ZSTD vs Snappy).

**Why keep the extra columns:** `raw_response_id` is a natural
idempotency/audit signal per scrape event, and `source_url` supports
"where did this number come from" auditability — both are the kind of
provenance data a real production rate-tracking system would want.
Discarding verified data the source already provides in favor of
matching a spec's minimal field list exactly would be a worse
engineering decision than a small schema deviation, documented here.

---

## 3. Idempotency / Natural Key Strategy

**Decision:** `UNIQUE (provider, rate_type, effective_date)`, with
upsert (not reject) on conflict.

**Alternative considered:** include `rate_value` in the uniqueness key,
so only byte-for-byte identical re-ingestion is treated as a duplicate.

**Why rejected:** real-world rate feeds republish corrected values for
the same day before the rate "settles" — confirmed by the actual data,
where ~97% of natural-key groups had multiple scrapes on the same day
with different `rate_value`s as the day progressed. If `rate_value`
were part of the key, a corrected rate would silently insert as a
second row for the same day rather than correcting the existing one —
a data integrity bug, not a feature. Treating `(provider, rate_type,
effective_date)` as the natural key and resolving same-day collisions
to "latest `ingestion_ts` wins" matches how financial data actually
behaves.

---

## 4. Malformed Row Handling

**Decision:** rows with null, negative, or unrealistically large
(`>50%`) `rate_value`, or missing `provider`/`rate_type`, are rejected
outright — not inserted, not clamped, not defaulted. Rejections are
recorded in `RawIngestion.error_summary`, grouped by reason with sample
rows, never silently dropped.

**Why not clamp or insert anyway:** a clamped or null-defaulted value in
a financial rates table is worse than a missing data point — it would
silently corrupt aggregate calculations (averages, 30-day changes)
without anyone noticing. Rejecting and logging makes the data quality
issue visible and auditable, consistent with the spec's "never crash
silently" requirement — silence isn't just about exceptions, it's about
bad data passing through invisibly.

---

## 5. Provider/Currency Name Normalization

**Decision:** case-insensitive resolution against existing `Provider`
rows at ingestion time (`HSBC` / `Hsbc` / `hsbc` → one row), and a small
alias map for currency strings (`usd` / `US Dollar` → `USD`).

**Why a real fix, not a workaround:** without this, a naive
`get_or_create(name=raw_value)` would create three separate "providers"
that are actually one bank — directly corrupting the "latest rate per
provider" query, since each casing variant would be tracked as a
distinct entity with its own (incomplete) rate history.

---

## 6. Caching Strategy

**Decision:** granular cache keys per `(provider, rate_type)`
combination, event-driven invalidation on every successful write
(ingest endpoint, management command, Celery task all call the same
`invalidate_latest_cache()`), with a TTL (`RATES_LATEST_CACHE_TTL_SECONDS`,
default 300s) as a backstop rather than the primary correctness
mechanism.

**Alternative considered:** TTL-only caching (no explicit invalidation),
which is simpler to implement.

**Why rejected:** `/rates/latest` is the highest-read-traffic endpoint
by design — it's the "what's the rate right now" view. A TTL-only
strategy means a client could `POST /rates/ingest` and then immediately
`GET /rates/latest` and see stale data for up to the TTL window. That's
a real correctness complaint for a rates API, not just a minor staleness
issue. Event-driven invalidation closes that gap; the TTL remains purely
as defense-in-depth for any future write path that might bypass the
cache service.

**Why granular keys, not one cache entry for the whole endpoint:**
invalidating one provider's rate shouldn't force recomputation of every
other provider's cached "latest" response. Granular keys mean
invalidation is precise and cheap.

---

## 7. Scheduling Strategy

**Decision:** Celery Beat with `django_celery_beat`'s `DatabaseScheduler`,
interval configured via `INGESTION_SCHEDULE_MINUTES` env var, registered
via a data migration so the periodic task exists automatically the
moment `docker-compose up` finishes migrating — no manual setup step.

**Why a migration instead of a one-off management command run by hand:**
a manual step is something a reviewer (or a future ops engineer) has to
remember to do; a migration runs automatically as part of the standard
deploy/boot sequence, which is more production-realistic and removes a
failure mode ("I forgot to register the periodic task").

**Why `DatabaseScheduler` instead of the default in-memory beat
scheduler:** the default scheduler loses its schedule on every restart
and can't be inspected/modified without redeploying code. The database
scheduler persists schedule state in Postgres and is inspectable via
Django admin — closer to how a real production Celery deployment is
typically run.

---

## 8. Authentication Scheme for POST /rates/ingest

**Decision:** a custom `StaticBearerTokenAuthentication` class checking
`Authorization: Bearer <static-token-from-env>` against
`INGESTION_API_TOKEN`.

**Why not DRF's built-in `TokenAuthentication`:** DRF's built-in scheme
sends `Authorization: Token <key>`, not `Bearer <key>`, and is backed by
a per-`User` token model. The spec explicitly calls for "Bearer Token
authentication" with "no external authentication providers" — a single
static bearer token is the simplest implementation that satisfies the
literal requirement.

**Acknowledged limitation:** a single static token has no per-client
identity, rotation, or revocation story. In a real production system,
this would be replaced with per-client API keys (DRF's `TokenAuthentication`
model, or a dedicated `APIClient` model with hashed keys), each
independently revocable. This is documented here as a deliberate scope
simplification, not an oversight.

---

## 9. "Latest Rate" Query: DISTINCT ON vs. Materialized Table

Covered in depth in `schema.md`. Summary: `DISTINCT ON` chosen for
current scale (~1M rows, small dimension cardinality); a materialized
"latest rate" table (refreshed on every write) is the documented
evolution path if read latency or table size grow by an order of
magnitude or more.

---

## 10. Database Migrations Only — No Raw SQL

All schema changes go through Django's migration framework, including
the Celery Beat periodic task registration (implemented as a Django
data migration calling the ORM, not a raw `INSERT` statement). This
keeps the entire schema history versioned, reviewable, and reversible
through one consistent mechanism, per the spec's explicit requirement.

---

## 11. Scalability Considerations (Beyond Current Scope)

- **Read replicas:** `/rates/latest` and `/rates/history` are pure
  reads and would be the first candidates to route to a read replica if
  write load on the primary became a concern.
- **Materialized latest-rate table:** see above — the natural next step
  if `DISTINCT ON` query latency becomes a bottleneck.
- **Partitioning `Rate` by `effective_date`:** at significantly larger
  row counts (tens of millions+), partitioning by month/quarter would
  keep individual index sizes manageable and allow old partitions to be
  archived independently.
- **Per-client API keys with rate limiting:** the ingest endpoint
  currently has no rate limiting; DRF's throttling classes would be the
  natural addition for a multi-tenant production deployment.

---

## 12. Known Limitations

- Single static bearer token (see §8) — no per-client revocation.
- No dedicated "30-day rate change" endpoint — the schema/services
  support computing it, but it isn't exposed as its own API route in
  this version.
- Currency is tracked but not used for any FX-aware comparison logic —
  the dataset is effectively single-currency (USD) today; multi-currency
  rate comparison is out of scope.
- `DISTINCT ON` is PostgreSQL-specific; migrating to a different RDBMS
  would require switching the "latest rate" query strategy (e.g. to a
  window-function approach, which is more portable but slightly more
  expensive).
