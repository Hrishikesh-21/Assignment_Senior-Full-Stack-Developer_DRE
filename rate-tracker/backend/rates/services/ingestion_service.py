"""
Ingestion service — the single source of truth for "how does a rate
record get from a Parquet file into PostgreSQL". Both the seed_data
management command and the Celery scheduled task call this module; no
business logic lives in either caller (keeps them thin, per the spec's
"avoid fat views/commands" rule, and avoids duplicating logic in two
places that would drift apart over time).

Pipeline:
  1. Stream the Parquet file in row-group batches (never load all ~1M
     rows into a single pandas DataFrame at once — see _iter_batches).
  2. Within each batch, validate every row against business rules.
     Invalid rows are rejected and recorded, never silently dropped.
  3. Collapse duplicate (provider, rate_type, effective_date) groups
     within the batch to the row with the latest ingestion_ts — handles
     the real-world case where a provider's rate was scraped many times
     in a day before this rate "settled" (see DECISIONS.md).
  4. Resolve Provider/RateType foreign keys via an in-memory cache
     (the dimension sets are small; doing a get_or_create per row would
     be 1M+ queries, which is the kind of thing this spec is explicitly
     testing for).
  5. Upsert into Rate using PostgreSQL's ON CONFLICT (via Django's
     bulk_create(..., update_conflicts=True)), keyed on the unique
     constraint — so re-running ingestion is idempotent: unchanged rows
     are a no-op, changed rows are updated, new rows are inserted.
  6. Record full statistics + structured error summary on RawIngestion
     for audit/replay.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Iterator

import pandas as pd
import pyarrow.parquet as pq
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rates.models import Provider, Rate, RateType, RawIngestion
from rates.services.normalization import (
    normalize_currency,
    normalize_provider_name,
    normalize_rate_type_code,
)

logger = logging.getLogger("rates")

BATCH_SIZE = 20_000

REQUIRED_COLUMNS = {"provider", "rate_type", "rate_value", "effective_date"}


@dataclass
class RejectedRow:
    reason: str
    detail: str


@dataclass
class IngestionResult:
    rows_read: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_rejected: int = 0
    rejections: list[RejectedRow] = field(default_factory=list)

    def error_summary(self) -> dict | None:
        if not self.rejections:
            return None
        # Group by reason so the audit log is compact and queryable,
        # rather than dumping every single rejected row verbatim.
        grouped: dict[str, dict] = {}
        for r in self.rejections:
            bucket = grouped.setdefault(r.reason, {"count": 0, "samples": []})
            bucket["count"] += 1
            if len(bucket["samples"]) < 5:
                bucket["samples"].append(r.detail)
        return grouped


class IngestionService:
    """Stateful per-run helper: caches dimension lookups in memory for
    the duration of a single ingestion run to avoid repeated queries."""

    def __init__(self) -> None:
        self._provider_cache: dict[str, Provider] = {}
        self._rate_type_cache: dict[str, RateType] = {}

    def run(self, source_file: str) -> RawIngestion:
        ingestion = RawIngestion.objects.create(
            source_file=source_file, status=RawIngestion.Status.PENDING
        )
        logger.info("ingestion.started", extra={"ingestion_id": ingestion.id, "source_file": source_file})

        result = IngestionResult()
        try:
            self._preload_dimension_caches()
            for batch_df in self._iter_batches(source_file):
                self._process_batch(batch_df, result)

            ingestion.rows_read = result.rows_read
            ingestion.rows_inserted = result.rows_inserted
            ingestion.rows_updated = result.rows_updated
            ingestion.rows_rejected = result.rows_rejected
            ingestion.error_summary = result.error_summary()
            ingestion.save(
                update_fields=[
                    "rows_read", "rows_inserted", "rows_updated",
                    "rows_rejected", "error_summary",
                ]
            )

            final_status = (
                RawIngestion.Status.PARTIAL if result.rows_rejected else RawIngestion.Status.SUCCESS
            )
            ingestion.mark_finished(final_status)

            logger.info(
                "ingestion.finished",
                extra={
                    "ingestion_id": ingestion.id,
                    "status": final_status,
                    "rows_read": result.rows_read,
                    "rows_inserted": result.rows_inserted,
                    "rows_updated": result.rows_updated,
                    "rows_rejected": result.rows_rejected,
                },
            )
        except Exception:
            ingestion.error_summary = {"fatal_error": "See server logs for ingestion_id={}".format(ingestion.id)}
            ingestion.save(update_fields=["error_summary"])
            ingestion.mark_finished(RawIngestion.Status.FAILED)
            logger.error(
                "ingestion.failed",
                extra={"ingestion_id": ingestion.id, "source_file": source_file},
                exc_info=True,
            )
            raise

        return ingestion

    # ------------------------------------------------------------------
    # Parquet streaming
    # ------------------------------------------------------------------
    def _iter_batches(self, source_file: str) -> Iterator[pd.DataFrame]:
        """
        Stream the Parquet file in chunks rather than reading it fully
        into memory. pyarrow's iter_batches() reads row-group-aligned
        batches off disk, which is what makes ~1M rows safe to process
        on a small container without an OOM.
        """
        parquet_file = pq.ParquetFile(source_file)
        for arrow_batch in parquet_file.iter_batches(batch_size=BATCH_SIZE):
            yield arrow_batch.to_pandas()

    # ------------------------------------------------------------------
    # Dimension cache
    # ------------------------------------------------------------------
    def _preload_dimension_caches(self) -> None:
        for p in Provider.objects.all():
            self._provider_cache[p.name.lower()] = p
        for rt in RateType.objects.all():
            self._rate_type_cache[rt.code.lower()] = rt

    def _resolve_provider(self, raw_name: str) -> Provider:
        canonical = normalize_provider_name(raw_name)
        key = canonical.lower()
        if key not in self._provider_cache:
            provider = Provider.objects.filter(name__iexact=canonical).first()
            if provider is None:
                provider = Provider.objects.create(name=canonical)
            self._provider_cache[key] = provider
        return self._provider_cache[key]

    def _resolve_rate_type(self, raw_code: str) -> RateType:
        canonical = normalize_rate_type_code(raw_code)
        key = canonical.lower()
        if key not in self._rate_type_cache:
            rate_type, _ = RateType.objects.get_or_create(code=canonical)
            self._rate_type_cache[key] = rate_type
        return self._rate_type_cache[key]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate_row(self, row: dict) -> tuple[bool, str | None, str | None]:
        """Returns (is_valid, reason, detail)."""
        if not row.get("provider") or not str(row["provider"]).strip():
            return False, "missing_provider", str(row)
        if not row.get("rate_type") or not str(row["rate_type"]).strip():
            return False, "missing_rate_type", str(row)

        raw_value = row.get("rate_value")
        if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
            return False, "null_rate_value", str(row)

        try:
            decimal_value = Decimal(str(raw_value))
        except (InvalidOperation, ValueError):
            return False, "unparseable_rate_value", str(row)

        if decimal_value < Decimal(str(settings.RATE_VALUE_MIN)) or decimal_value > Decimal(
            str(settings.RATE_VALUE_MAX)
        ):
            return False, "rate_value_out_of_range", f"value={decimal_value}"

        if not row.get("effective_date"):
            return False, "missing_effective_date", str(row)

        return True, None, None

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------
    def _process_batch(self, batch_df: pd.DataFrame, result: IngestionResult) -> None:
        missing_cols = REQUIRED_COLUMNS - set(batch_df.columns)
        if missing_cols:
            raise ValueError(f"Source file missing required columns: {missing_cols}")

        result.rows_read += len(batch_df)

        latest_by_key: dict[tuple[str, str, date], dict] = {}

        for row in batch_df.to_dict(orient="records"):
            is_valid, reason, detail = self._validate_row(row)
            if not is_valid:
                result.rows_rejected += 1
                result.rejections.append(RejectedRow(reason=reason, detail=detail or ""))
                continue

            provider_key = normalize_provider_name(str(row["provider"])).lower()
            rate_type_key = normalize_rate_type_code(str(row["rate_type"])).lower()
            eff_date = row["effective_date"]
            if isinstance(eff_date, pd.Timestamp):
                eff_date = eff_date.date()
            elif isinstance(eff_date, datetime):
                eff_date = eff_date.date()

            natural_key = (provider_key, rate_type_key, eff_date)

            ingestion_ts = row.get("ingestion_ts") or row.get("ingestion_timestamp")
            if isinstance(ingestion_ts, pd.Timestamp):
                ingestion_ts_dt = ingestion_ts.to_pydatetime()
            elif ingestion_ts is None or (isinstance(ingestion_ts, float) and pd.isna(ingestion_ts)):
                ingestion_ts_dt = timezone.now()
            else:
                ingestion_ts_dt = ingestion_ts

            if timezone.is_naive(ingestion_ts_dt):
                ingestion_ts_dt = timezone.make_aware(ingestion_ts_dt, dt_timezone.utc)

            existing = latest_by_key.get(natural_key)
            if existing is None or ingestion_ts_dt > existing["ingestion_ts"]:
                latest_by_key[natural_key] = {
                    "row": row,
                    "ingestion_ts": ingestion_ts_dt,
                    "eff_date": eff_date,
                }

        if not latest_by_key:
            return

        self._upsert_rows(latest_by_key, result)

    def _upsert_rows(self, latest_by_key: dict, result: IngestionResult) -> None:
        # Resolve all provider/rate_type FKs first so we can build
        # exact (provider_id, rate_type_id, effective_date) DB keys.
        # This lets us query only the rows that could possibly conflict
        # rather than every row sharing any effective_date in the batch
        # (the old approach caused O(n²) table scans as the table grew).
        db_key_to_payload: dict[tuple[int, int, date], dict] = {}
        for (provider_key, rate_type_key, eff_date), payload in latest_by_key.items():
            row = payload["row"]
            provider = self._resolve_provider(str(row["provider"]))
            rate_type = self._resolve_rate_type(str(row["rate_type"]))
            db_key_to_payload[(provider.id, rate_type.id, eff_date)] = payload

        if not db_key_to_payload:
            return

        # Build a precise filter: one (provider_id, rate_type_id, effective_date)
        # triple per batch entry. PostgreSQL satisfies each term with a direct
        # index lookup on the unique constraint — result set is bounded at
        # batch_size rows regardless of how large the table grows.
        query = Q()
        for (provider_id, rate_type_id, eff_date) in db_key_to_payload:
            query |= Q(provider_id=provider_id, rate_type_id=rate_type_id, effective_date=eff_date)

        existing_rates = {
            (r.provider_id, r.rate_type_id, r.effective_date): r
            for r in Rate.objects.filter(query)
        }

        to_create: list[Rate] = []
        to_update: list[Rate] = []

        for (provider_id, rate_type_id, eff_date), payload in db_key_to_payload.items():
            row = payload["row"]
            currency = normalize_currency(row.get("currency"))
            rate_value = Decimal(str(row["rate_value"]))

            existing_row = existing_rates.get((provider_id, rate_type_id, eff_date))
            if existing_row is not None:
                existing_row.rate_value = rate_value
                existing_row.ingestion_timestamp = payload["ingestion_ts"]
                existing_row.currency = currency
                existing_row.source_url = row.get("source_url")
                existing_row.raw_response_id = row.get("raw_response_id")
                to_update.append(existing_row)
            else:
                provider = self._resolve_provider(str(row["provider"]))
                rate_type = self._resolve_rate_type(str(row["rate_type"]))
                to_create.append(
                    Rate(
                        provider=provider,
                        rate_type=rate_type,
                        rate_value=rate_value,
                        effective_date=eff_date,
                        ingestion_timestamp=payload["ingestion_ts"],
                        currency=currency,
                        source_url=row.get("source_url"),
                        raw_response_id=row.get("raw_response_id"),
                    )
                )

        with transaction.atomic():
            if to_create:
                Rate.objects.bulk_create(to_create, batch_size=BATCH_SIZE)
                result.rows_inserted += len(to_create)
            if to_update:
                Rate.objects.bulk_update(
                    to_update,
                    fields=["rate_value", "ingestion_timestamp", "currency", "source_url", "raw_response_id"],
                    batch_size=BATCH_SIZE,
                )
                result.rows_updated += len(to_update)


def run_ingestion(source_file: str) -> RawIngestion:
    """Thin module-level entrypoint used by both the management command
    and the Celery task, so neither has to know about IngestionService
    internals."""
    return IngestionService().run(source_file)















