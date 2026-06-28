import datetime
from decimal import Decimal

import pytest

from rates.models import Provider, Rate, RateType
from rates.services.rate_query_service import RateQueryService


@pytest.mark.django_db
class TestGetLatestRates:
    def test_returns_one_row_per_provider_and_type(self, provider, rate_type):
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.75"),
            effective_date=datetime.date(2026, 1, 2),
            ingestion_timestamp=datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc),
        )

        results = list(RateQueryService.get_latest_rates())

        assert len(results) == 1
        assert results[0].rate_value == Decimal("6.75")
        assert results[0].effective_date == datetime.date(2026, 1, 2)

    def test_filters_by_provider(self, provider, rate_type):
        other_provider = Provider.objects.create(name="Chase")
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        Rate.objects.create(
            provider=other_provider, rate_type=rate_type, rate_value=Decimal("7.0"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )

        results = list(RateQueryService.get_latest_rates(provider_id=provider.id))

        assert len(results) == 1
        assert results[0].provider_id == provider.id

    def test_filters_by_rate_type(self, provider, rate_type):
        other_type = RateType.objects.create(code="SAVINGS_APY")
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        Rate.objects.create(
            provider=provider, rate_type=other_type, rate_value=Decimal("2.0"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )

        results = list(RateQueryService.get_latest_rates(rate_type_id=rate_type.id))

        assert len(results) == 1
        assert results[0].rate_type_id == rate_type.id


@pytest.mark.django_db
class TestGetHistory:
    def test_filters_by_date_range(self, provider, rate_type):
        for day in range(1, 6):
            Rate.objects.create(
                provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
                effective_date=datetime.date(2026, 1, day),
                ingestion_timestamp=datetime.datetime(2026, 1, day, tzinfo=datetime.timezone.utc),
            )

        results = list(
            RateQueryService.get_history(
                date_from=datetime.date(2026, 1, 2), date_to=datetime.date(2026, 1, 4)
            )
        )

        assert len(results) == 3

    def test_orders_newest_first(self, provider, rate_type):
        for day in range(1, 4):
            Rate.objects.create(
                provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
                effective_date=datetime.date(2026, 1, day),
                ingestion_timestamp=datetime.datetime(2026, 1, day, tzinfo=datetime.timezone.utc),
            )

        results = list(RateQueryService.get_history())

        assert results[0].effective_date == datetime.date(2026, 1, 3)
        assert results[-1].effective_date == datetime.date(2026, 1, 1)
