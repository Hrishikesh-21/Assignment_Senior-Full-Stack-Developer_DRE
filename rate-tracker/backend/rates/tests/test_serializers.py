import datetime
from decimal import Decimal

import pytest

from rates.models import Provider, Rate, RateType
from rates.serializers import RateIngestSerializer, RateReadSerializer


@pytest.mark.django_db
class TestRateReadSerializer:
    def test_serializes_nested_provider_and_rate_type(self, rate):
        data = RateReadSerializer(rate).data

        assert data["provider"]["name"] == "HSBC"
        assert data["rate_type"]["code"] == "MORTGAGE_30Y"
        assert data["rate_value"] == "6.7500"


@pytest.mark.django_db
class TestRateIngestSerializer:
    def test_valid_payload_creates_rate(self):
        serializer = RateIngestSerializer(data={
            "provider": "Wells Fargo",
            "rate_type": "mortgage_15y",
            "rate_value": "6.25",
            "effective_date": "2026-03-01",
        })
        assert serializer.is_valid(), serializer.errors

        rate = serializer.save()

        assert rate.provider.name == "Wells Fargo"
        assert rate.rate_type.code == "MORTGAGE_15Y"
        assert rate.rate_value == Decimal("6.25")

    def test_rejects_out_of_range_rate_value(self):
        serializer = RateIngestSerializer(data={
            "provider": "Wells Fargo",
            "rate_type": "MORTGAGE_15Y",
            "rate_value": "999.0",
            "effective_date": "2026-03-01",
        })
        assert not serializer.is_valid()
        assert "rate_value" in serializer.errors

    def test_rejects_missing_required_field(self):
        serializer = RateIngestSerializer(data={
            "rate_type": "MORTGAGE_15Y",
            "rate_value": "6.25",
            "effective_date": "2026-03-01",
        })
        assert not serializer.is_valid()
        assert "provider" in serializer.errors

    def test_rejects_malformed_date(self):
        serializer = RateIngestSerializer(data={
            "provider": "Wells Fargo",
            "rate_type": "MORTGAGE_15Y",
            "rate_value": "6.25",
            "effective_date": "not-a-date",
        })
        assert not serializer.is_valid()
        assert "effective_date" in serializer.errors

    def test_reposting_same_natural_key_updates_existing_rate(self):
        first = RateIngestSerializer(data={
            "provider": "Wells Fargo", "rate_type": "MORTGAGE_15Y",
            "rate_value": "6.25", "effective_date": "2026-03-01",
        })
        first.is_valid()
        first.save()

        second = RateIngestSerializer(data={
            "provider": "Wells Fargo", "rate_type": "MORTGAGE_15Y",
            "rate_value": "6.40", "effective_date": "2026-03-01",
        })
        second.is_valid()
        second.save()

        assert Rate.objects.count() == 1
        assert Rate.objects.first().rate_value == Decimal("6.40")

    def test_provider_casing_resolves_to_existing_provider(self):
        Provider.objects.create(name="HSBC")

        serializer = RateIngestSerializer(data={
            "provider": "hsbc", "rate_type": "SAVINGS",
            "rate_value": "1.5", "effective_date": "2026-03-01",
        })
        serializer.is_valid()
        serializer.save()

        assert Provider.objects.count() == 1
