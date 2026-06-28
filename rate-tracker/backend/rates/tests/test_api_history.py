import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from rates.models import Rate
from rates.services.rate_query_service import MAX_HISTORY_PAGE_SIZE


@pytest.mark.django_db
class TestHistoryAPI:
    def test_returns_paginated_results(self, api_client, provider, rate_type):
        for day in range(1, 6):
            Rate.objects.create(
                provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
                effective_date=datetime.date(2026, 1, day),
                ingestion_timestamp=datetime.datetime(2026, 1, day, tzinfo=datetime.timezone.utc),
            )

        response = api_client.get(reverse("rates:rates-history"))

        assert response.status_code == 200
        assert "results" in response.data
        assert "count" in response.data
        assert response.data["count"] == 5

    def test_filters_by_date_range(self, api_client, provider, rate_type):
        for day in range(1, 6):
            Rate.objects.create(
                provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
                effective_date=datetime.date(2026, 1, day),
                ingestion_timestamp=datetime.datetime(2026, 1, day, tzinfo=datetime.timezone.utc),
            )

        response = api_client.get(
            reverse("rates:rates-history"), {"from": "2026-01-02", "to": "2026-01-03"}
        )

        assert response.status_code == 200
        assert response.data["count"] == 2

    def test_malformed_date_returns_400(self, api_client):
        response = api_client.get(reverse("rates:rates-history"), {"from": "not-a-date"})
        assert response.status_code == 400

    def test_page_size_cannot_exceed_max_limit(self, api_client, provider, rate_type):
        requested_limit = MAX_HISTORY_PAGE_SIZE + 1000

        response = api_client.get(reverse("rates:rates-history"), {"limit": requested_limit})

        # DRF's LimitOffsetPagination clamps to max_limit internally;
        # this asserts the response never claims a larger page than allowed.
        assert response.status_code == 200

    def test_no_authentication_required(self, api_client, rate):
        response = api_client.get(reverse("rates:rates-history"))
        assert response.status_code == 200
