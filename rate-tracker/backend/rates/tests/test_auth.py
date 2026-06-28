import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestBearerTokenAuthentication:
    def test_correct_bearer_scheme_is_accepted(self, api_client, ingest_auth_headers):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "6.75", "effective_date": "2026-01-01",
        }
        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json", **ingest_auth_headers
        )
        assert response.status_code == 201

    def test_wrong_scheme_keyword_is_rejected(self, api_client, settings):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "6.75", "effective_date": "2026-01-01",
        }
        # Using "Token" instead of "Bearer" should not authenticate.
        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json",
            HTTP_AUTHORIZATION=f"Token {settings.INGESTION_API_TOKEN}",
        )
        assert response.status_code == 401

    def test_malformed_header_is_rejected(self, api_client):
        payload = {
            "provider": "HSBC", "rate_type": "MORTGAGE_30Y",
            "rate_value": "6.75", "effective_date": "2026-01-01",
        }
        response = api_client.post(
            reverse("rates:rates-ingest"), payload, format="json",
            HTTP_AUTHORIZATION="Bearer",  # missing the actual token part
        )
        assert response.status_code == 401

    def test_get_endpoints_ignore_bearer_header_entirely(self, api_client, rate):
        # GET endpoints have authentication_classes = [] — a bearer
        # header (even an invalid one) should simply be ignored, not
        # cause an error, since these endpoints don't require auth at all.
        response = api_client.get(
            reverse("rates:rates-latest"), HTTP_AUTHORIZATION="Bearer garbage-token"
        )
        assert response.status_code == 200
