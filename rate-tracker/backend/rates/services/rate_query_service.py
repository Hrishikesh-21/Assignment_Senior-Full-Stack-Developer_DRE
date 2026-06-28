"""
Query service — encapsulates the read-side query patterns the API needs.
Kept out of views.py so views stay thin (a view's job is request/response
handling, not building querysets) and so these queries are independently
unit-testable against the DB without going through DRF at all.
"""
from datetime import date

from django.db.models import QuerySet

from rates.models import Rate

# Hard ceiling on history page size — the spec explicitly requires
# "never allow unlimited responses". Even if a client requests a huge
# page size via pagination params, this caps it.
MAX_HISTORY_PAGE_SIZE = 500


class RateQueryService:
    @staticmethod
    def get_latest_rates(provider_id: int | None = None, rate_type_id: int | None = None) -> QuerySet:
        """
        Latest rate per (provider, rate_type), optionally filtered.

        Uses PostgreSQL's DISTINCT ON, which combined with the
        (provider, rate_type, -effective_date) index defined on Rate
        lets Postgres satisfy this via an index scan rather than a full
        table scan + sort. This is intentionally Postgres-specific (see
        DECISIONS.md for the tradeoff discussion vs. a materialized
        "latest rate" table, which is the recommended evolution path at
        much larger scale).
        """
        qs = Rate.objects.select_related("provider", "rate_type")

        if provider_id is not None:
            qs = qs.filter(provider_id=provider_id)
        if rate_type_id is not None:
            qs = qs.filter(rate_type_id=rate_type_id)

        # order_by must start with the DISTINCT ON fields, per Postgres
        # rules, followed by the tiebreaker (-effective_date) that
        # determines which row within each group "wins".
        qs = qs.order_by("provider_id", "rate_type_id", "-effective_date").distinct(
            "provider_id", "rate_type_id"
        )
        return qs

    @staticmethod
    def get_history(
        provider_id: int | None = None,
        rate_type_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> QuerySet:
        """
        Historical rate lookup with optional filters. Pagination is
        applied at the view/serializer layer via DRF's pagination
        classes, which already enforces PAGE_SIZE — this method just
        builds the filtered, indexed queryset.
        """
        qs = Rate.objects.select_related("provider", "rate_type")

        if provider_id is not None:
            qs = qs.filter(provider_id=provider_id)
        if rate_type_id is not None:
            qs = qs.filter(rate_type_id=rate_type_id)
        if date_from is not None:
            qs = qs.filter(effective_date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(effective_date__lte=date_to)

        return qs.order_by("-effective_date", "provider_id", "rate_type_id")
