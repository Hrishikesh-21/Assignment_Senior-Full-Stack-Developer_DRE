"""
Rate — the core fact table (~1M+ rows).

Design notes (see schema.md for the full write-up):

- rate_value is DECIMAL, never FLOAT. This is financial data; binary
  floating point introduces rounding error that compounds across
  aggregations like 30-day rate-change calculations.

- The unique constraint on (provider, rate_type, effective_date) is both
  the idempotency mechanism for ingestion AND the most common lookup
  pattern, so it pulls double duty as a data-integrity constraint and a
  query-performance index.

- currency / source_url / raw_response_id are NOT in the original spec's
  "required fields" list, but the real source data includes them and they
  carry genuine provenance value (raw_response_id is effectively a
  natural idempotency key per scrape event; source_url supports
  auditability). Discarding verifiable data the source already provides
  would be a worse engineering decision than keeping three optional
  columns. See DECISIONS.md for the full rationale.
"""
from django.db import models


class Rate(models.Model):
    provider = models.ForeignKey(
        "rates.Provider",
        on_delete=models.PROTECT,
        related_name="rates",
    )
    rate_type = models.ForeignKey(
        "rates.RateType",
        on_delete=models.PROTECT,
        related_name="rates",
    )
    rate_value = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Rate as a percentage value, e.g. 6.7500 for 6.75%.",
    )
    effective_date = models.DateField(
        help_text="The date this rate is/was in effect (business date, not ingestion time).",
    )
    ingestion_timestamp = models.DateTimeField(
        help_text="When this specific observation was scraped/ingested from the source.",
    )

    # Optional provenance fields — present in the real source data,
    # not in the original spec's required-field list. See module docstring.
    currency = models.CharField(max_length=8, null=True, blank=True, default="USD")
    source_url = models.URLField(max_length=1024, null=True, blank=True)
    raw_response_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "rate_type", "effective_date"],
                name="uniq_provider_ratetype_effective_date",
            )
        ]
        indexes = [
            # Supports "latest rate per provider+type" via DISTINCT ON,
            # and general history lookups filtered/ordered by date.
            models.Index(
                fields=["provider", "rate_type", "-effective_date"],
                name="idx_rate_provider_type_date",
            ),
            models.Index(fields=["effective_date"], name="idx_rate_effective_date"),
            models.Index(fields=["ingestion_timestamp"], name="idx_rate_ingestion_ts"),
        ]
        ordering = ["-effective_date"]

    def __str__(self) -> str:
        return f"{self.provider} / {self.rate_type} @ {self.effective_date} = {self.rate_value}"
