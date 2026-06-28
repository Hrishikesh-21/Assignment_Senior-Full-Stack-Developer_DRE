import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from rates.models import Provider, Rate, RateType


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def provider(db):
    return Provider.objects.create(name="HSBC")


@pytest.fixture
def rate_type(db):
    return RateType.objects.create(code="MORTGAGE_30Y")


@pytest.fixture
def rate(db, provider, rate_type):
    return Rate.objects.create(
        provider=provider,
        rate_type=rate_type,
        rate_value=Decimal("6.7500"),
        effective_date=datetime.date(2026, 1, 1),
        ingestion_timestamp=datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc),
        currency="USD",
    )


@pytest.fixture
def ingest_auth_headers(settings):
    return {"HTTP_AUTHORIZATION": f"Bearer {settings.INGESTION_API_TOKEN}"}


@pytest.fixture(autouse=True)
def celery_eager_mode(settings):
    """
    Run Celery tasks synchronously in tests (no broker required) so
    task tests can call .apply() and inspect results/exceptions
    immediately, rather than needing a running worker.
    """
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
