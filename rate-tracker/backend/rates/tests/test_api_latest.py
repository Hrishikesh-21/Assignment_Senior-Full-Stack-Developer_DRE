import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from rates.models import Rate


@pytest.mark.django_db
class TestLatestRatesAPI:
    def test_returns_latest_rate_per_provider_and_type(self, api_client, provider, rate_type):
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.9"),
            effective_date=datetime.date(2026, 1, 2),
            ingestion_timestamp=datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc),
        )

        response = api_client.get(reverse("rates:rates-latest"))

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["rate_value"] == "6.9000"

    def test_filters_by_provider_query_param(self, api_client, provider, rate_type):
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )

        response = api_client.get(reverse("rates:rates-latest"), {"provider": "HSBC"})

        assert response.status_code == 200
        assert len(response.data) == 1

    def test_unknown_provider_returns_400_not_500(self, api_client):
        response = api_client.get(reverse("rates:rates-latest"), {"provider": "DoesNotExist"})

        assert response.status_code == 400

    def test_no_authentication_required(self, api_client, rate):
        # No Authorization header sent at all.
        response = api_client.get(reverse("rates:rates-latest"))
        assert response.status_code == 200

    def test_empty_result_when_no_rates(self, api_client):
        response = api_client.get(reverse("rates:rates-latest"))
        assert response.status_code == 200
        assert response.data == []
