# Schema Documentation

## Entity-Relationship Overview

```
Provider (1) ──────< (M) Rate (M) >────── (1) RateType
                          │
                          │ (audited by, not FK-linked —
                          │  RawIngestion tracks ingestion runs,
                          │  not individual rows)
                          ▼
                    RawIngestion
```

`Rate` is the central fact table. `Provider` and `RateType` are small
normalized lookup (dimension) tables. `RawIngestion` is an independent
audit log of ingestion runs — it is intentionally **not** foreign-keyed
to individual `Rate` rows, because a single ingestion run touches
thousands of rows and a per-row FK back to the run would add write
overhead with little query benefit; the audit need (counts, errors,
timing) is satisfied by aggregate statistics stored directly on
`RawIngestion`.

---

## Tables

### `Provider`

| Column | Type | Notes |
|---|---|---|
| id | BigAutoField (PK) | |
| name | VARCHAR(255), UNIQUE | Canonical display name |
| created_at | TIMESTAMPTZ | |

**Why normalized rather than a free-text field on `Rate`:** the real
source data contains casing inconsistencies for the same institution
(`HSBC`, `Hsbc`, `hsbc`). A lookup table with case-insensitive
resolution at ingestion time is the only way to guarantee one canonical
row per real-world provider. It also avoids storing the same string
across hundreds of thousands of `Rate` rows.

### `RateType`

| Column | Type | Notes |
|---|---|---|
| id | BigAutoField (PK) | |
| code | VARCHAR(64), UNIQUE | e.g. `MORTGAGE_30Y` |
| created_at | TIMESTAMPTZ | |

Same normalization rationale as `Provider`.

### `Rate` (fact table, ~1M+ rows)

| Column | Type | Notes |
|---|---|---|
| id | BigAutoField (PK) | |
| provider_id | FK -> Provider | `on_delete=PROTECT` |
| rate_type_id | FK -> RateType | `on_delete=PROTECT` |
| rate_value | DECIMAL(10,4) | **Never FLOAT** — see rationale below |
| effective_date | DATE | Business date the rate applies to |
| ingestion_timestamp | TIMESTAMPTZ | When this specific observation was scraped |
| currency | VARCHAR(8), nullable | Defaults to USD; normalized from source aliases |
| source_url | VARCHAR(1024), nullable | Provenance — not in original spec, kept from real source data |
| raw_response_id | VARCHAR(255), nullable | Provenance — unique-per-scrape-event id from source |
| created_at / updated_at | TIMESTAMPTZ | |

**Constraint:** `UNIQUE (provider_id, rate_type_id, effective_date)` —
this is the natural key. It serves two purposes simultaneously: data
integrity (one rate per provider/type/day) and idempotency (re-ingesting
the same logical record performs an upsert rather than creating a
duplicate).

**Why DECIMAL, not FLOAT, for `rate_value`:** rate values are financial
percentages. IEEE-754 floating point cannot represent most decimal
fractions exactly, and that error compounds across aggregations (e.g. a
30-day rate-change calculation: `new_rate - old_rate`). `DECIMAL(10,4)`
stores the value exactly as provided.

#### Indexes on `Rate`

| Index | Columns | Supports |
|---|---|---|
| `idx_rate_provider_type_date` | `(provider_id, rate_type_id, -effective_date)` | "Latest rate per provider+type" via `DISTINCT ON`; also general filtered history queries |
| `idx_rate_effective_date` | `(effective_date)` | Date-range history queries without a provider/type filter |
| `idx_rate_ingestion_ts` | `(ingestion_timestamp)` | "Ingestion time window" queries (e.g. "what was ingested in the last hour") |
| (implicit) unique constraint index | `(provider_id, rate_type_id, effective_date)` | Idempotency + most common point lookup |

### `RawIngestion` (audit log)

| Column | Type | Notes |
|---|---|---|
| id | BigAutoField (PK) | |
| source_file | VARCHAR(512) | |
| started_at | TIMESTAMPTZ | |
| finished_at | TIMESTAMPTZ, nullable | Null while ingestion is in progress |
| status | VARCHAR(16) | `PENDING` / `SUCCESS` / `PARTIAL` / `FAILED` |
| rows_read / rows_inserted / rows_updated / rows_rejected | INTEGER | |
| error_summary | JSONB, nullable | Structured `{reason: {count, samples}}`, never a raw stack trace |

`error_summary` is intentionally structured and grouped by rejection
reason (with up to 5 sample rows per reason) rather than dumping every
rejected row — this keeps the audit log queryable and bounded in size
even if a malformed source file produces millions of rejections.

---

## Query Optimization Strategy

### "Latest rate per provider" / "latest rate per provider and type"

Implemented via PostgreSQL's `DISTINCT ON`:

```sql
SELECT DISTINCT ON (provider_id, rate_type_id) *
FROM rates_rate
ORDER BY provider_id, rate_type_id, effective_date DESC;
```

This is satisfied efficiently by `idx_rate_provider_type_date` — Postgres
can walk the index in order and take the first row per group without a
separate sort step.

**Tradeoff considered:** a materialized "latest rate" table (one row per
provider+type, updated on every write) would make this read essentially
free (no grouping at all), at the cost of write-time complexity (every
insert/update must also maintain the materialized table) and a second
source of truth that can drift if not maintained carefully. At the
current scale (~1M rows, small provider/type cardinality), `DISTINCT ON`
with the composite index performs well within acceptable latency. The
materialized-table approach is the recommended evolution path if this
system needed to scale to tens of millions of rows or sub-millisecond
read latency — see DECISIONS.md.

### "Historical rate lookup" / date-range queries

Filtered and ordered using `idx_rate_effective_date` (or the composite
index when also filtered by provider/type). Always paginated server-side
with a hard ceiling (`MAX_HISTORY_PAGE_SIZE = 500`) regardless of client
request — satisfies "never allow unlimited responses."

### "30-day rate changes"

Not implemented as a dedicated endpoint in this version (out of scope
for the core API spec), but the schema supports it directly: a 30-day
change is `get_history(date_from=today-30d, date_to=today)` for a given
provider+type, with the change computed as
`latest.rate_value - earliest.rate_value` in the application layer. See
"Future Improvements" in README.md.

### "Ingestion time window queries"

`idx_rate_ingestion_ts` supports `WHERE ingestion_timestamp BETWEEN x AND y`
directly, useful for operational questions like "what changed in the
last hour" independent of `effective_date`.

---

## Design Tradeoffs Summary

| Decision | Tradeoff accepted |
|---|---|
| Normalize Provider/RateType | Extra JOIN on every query, in exchange for data integrity and smaller fact table |
| `DISTINCT ON` over materialized view | Slightly more read-time computation, in exchange for simpler write path and no second source of truth |
| `on_delete=PROTECT` on Rate's FKs | Cannot delete a Provider/RateType that has historical rates — intentional, since rate history should never be silently cascaded away |
| Optional provenance fields (`source_url`, `raw_response_id`, `currency`) kept on `Rate` rather than discarded | Slightly wider table than the original spec's minimal field list, in exchange for not throwing away real audit data |
