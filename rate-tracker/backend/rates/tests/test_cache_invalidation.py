import datetime
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse

from rates.models import Rate
from rates.services.cache_service import (
    build_latest_cache_key,
    get_cached_latest,
    invalidate_latest_cache,
    set_cached_latest,
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestCacheService:
    def test_set_and_get_cached_latest(self):
        set_cached_latest(1, 2, {"foo": "bar"})
        assert get_cached_latest(1, 2) == {"foo": "bar"}

    def test_cache_miss_returns_none(self):
        assert get_cached_latest(999, 999) is None

    def test_invalidate_clears_specific_key(self):
        set_cached_latest(1, 2, {"foo": "bar"})
        invalidate_latest_cache(provider_id=1, rate_type_id=2)
        assert get_cached_latest(1, 2) is None

    def test_invalidate_also_clears_aggregate_all_keys(self):
        set_cached_latest(None, None, {"all": "data"})
        invalidate_latest_cache(provider_id=1, rate_type_id=2)
        assert get_cached_latest(None, None) is None

    def test_invalidate_does_not_clear_unrelated_keys(self):
        set_cached_latest(5, 6, {"unrelated": "data"})
        invalidate_latest_cache(provider_id=1, rate_type_id=2)
        assert get_cached_latest(5, 6) == {"unrelated": "data"}


@pytest.mark.django_db
class TestCacheIntegrationWithAPI:
    def test_latest_endpoint_populates_cache_on_miss(self, api_client, rate):
        key = build_latest_cache_key(None, None)
        assert get_cached_latest(None, None) is None

        api_client.get(reverse("rates:rates-latest"))

        assert get_cached_latest(None, None) is not None

    def test_ingest_invalidates_relevant_cache(self, api_client, ingest_auth_headers, provider, rate_type):
        Rate.objects.create(
            provider=provider, rate_type=rate_type, rate_value=Decimal("6.5"),
            effective_date=datetime.date(2026, 1, 1),
            ingestion_timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        )
        # Warm the cache.
        api_client.get(reverse("rates:rates-latest"))
        assert get_cached_latest(None, None) is not None

        # New ingest should invalidate the "all" aggregate cache key.
        api_client.post(
            reverse("rates:rates-ingest"),
            {
                "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
                "rate_value": "7.0", "effective_date": "2026-01-05",
            },
            format="json",
            **ingest_auth_headers,
        )

        assert get_cached_latest(None, None) is None
