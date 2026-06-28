import pytest
from django.urls import reverse

from rates.models import Rate


@pytest.mark.django_db
class TestIngestAPI:
    def test_valid_payload_creates_rate_and_returns_201(self, api_client, ingest_auth_headers):
        payload = {
            "provider": "HSBC",
            "rate_type": "MORTGAGE_30Y",
            "rate_value": "6.75",
            "effective_date": "2026-01-01",
        }

        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json", **ingest_auth_headers
        )

        assert response.status_code == 201
        assert Rate.objects.count() == 1

    def test_missing_token_returns_401(self, api_client):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "6.75", "effective_date": "2026-01-01",
        }

        response = api_client.post(reverse("rates:rates-ingest"), payload, format="json")

        assert response.status_code == 401

    def test_invalid_token_returns_401(self, api_client):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "6.75", "effective_date": "2026-01-01",
        }

        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json",
            HTTP_AUTHORIZATION="Bearer wrong-token",
        )

        assert response.status_code == 401

    def test_invalid_payload_returns_structured_400(self, api_client, ingest_auth_headers):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "not-a-number", "effective_date": "2026-01-01",
        }

        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json", **ingest_auth_headers
        )

        assert response.status_code == 400
        assert response.data["error"] is True
        assert "rate_value" in response.data["detail"]

    def test_response_never_contains_stack_trace(self, api_client, ingest_auth_headers):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "999999", "effective_date": "2026-01-01",
        }

        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json", **ingest_auth_headers
        )

        assert "Traceback" not in str(response.data)
        assert "File \"" not in str(response.data)

    def test_reposting_same_key_updates_not_duplicates(self, api_client, ingest_auth_headers):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "6.75", "effective_date": "2026-01-01",
        }
        api_client.post(reverse("rates:rates-ingest"), payload, format="json", **ingest_auth_headers)

        payload["rate_value"] = "7.00"
        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json", **ingest_auth_headers
        )

        assert response.status_code == 201
        assert Rate.objects.count() == 1
        assert Rate.objects.first().rate_value == 7.00
