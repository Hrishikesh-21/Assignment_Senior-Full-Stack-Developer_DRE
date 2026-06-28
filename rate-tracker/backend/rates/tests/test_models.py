import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from rates.models import Provider, Rate, RateType, RawIngestion


@pytest.mark.django_db
class TestProviderModel:
    def test_name_must_be_unique(self):
        Provider.objects.create(name="HSBC")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Provider.objects.create(name="HSBC")

    def test_str_representation(self):
        provider = Provider.objects.create(name="HSBC")
        assert str(provider) == "HSBC"


@pytest.mark.django_db
class TestRateTypeModel:
    def test_code_must_be_unique(self):
        RateType.objects.create(code="MORTGAGE_30Y")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                RateType.objects.create(code="MORTGAGE_30Y")


@pytest.mark.django_db
class TestRateModel:
    def test_unique_constraint_on_natural_key(self, provider, rate_type):
        Rate.objects.create(
            provider=provider,
            rate_type=rate_type,
            rate_value=Decimal("6.75"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Rate.objects.create(
                    provider=provider,
                    rate_type=rate_type,
                    rate_value=Decimal("6.80"),
                    effective_date=datetime.date(2026, 1, 1),
                    ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
                )

    def test_rate_value_preserves_decimal_precision(self, provider, rate_type):
        rate = Rate.objects.create(
            provider=provider,
            rate_type=rate_type,
            rate_value=Decimal("6.7534"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        rate.refresh_from_db()
        assert rate.rate_value == Decimal("6.7534")

    def test_different_dates_allowed_for_same_provider_and_type(self, provider, rate_type):
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.75"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        # Should not raise — different effective_date is a different natural key.
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.80"),
            effective_date=datetime.date(2026, 1, 2),
            ingestion_timestamp=datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc),
        )
        assert Rate.objects.count() == 2


@pytest.mark.django_db
class TestRawIngestionModel:
    def test_mark_finished_sets_status_and_timestamp(self):
        ingestion = RawIngestion.objects.create(source_file="test.parquet")
        assert ingestion.finished_at is None

        ingestion.mark_finished(RawIngestion.Status.SUCCESS)
        ingestion.refresh_from_db()

        assert ingestion.status == RawIngestion.Status.SUCCESS
        assert ingestion.finished_at is not None
