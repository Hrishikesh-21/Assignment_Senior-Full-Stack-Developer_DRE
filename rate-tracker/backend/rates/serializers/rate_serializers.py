"""
Serializers.

Two distinct serializers for Rate rather than one reused for everything:
  - RateReadSerializer: flattens provider/rate_type FKs into readable
    strings for GET responses (clients shouldn't need a second request
    just to resolve a provider_id into a name).
  - RateIngestSerializer: validates incoming POST payloads strictly,
    resolves/creates the Provider and RateType FKs from raw strings, and
    enforces the same business rules as the bulk ingestion path (range
    checks, required fields) so the single-record path can't bypass
    the same data quality bar.
"""
from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from rates.models import Provider, Rate, RateType
from rates.services.normalization import (
    normalize_currency,
    normalize_provider_name,
    normalize_rate_type_code,
)


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = ["id", "name"]


class RateTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateType
        fields = ["id", "code"]


class RateReadSerializer(serializers.ModelSerializer):
    provider = ProviderSerializer(read_only=True)
    rate_type = RateTypeSerializer(read_only=True)

    class Meta:
        model = Rate
        fields = [
            "id",
            "provider",
            "rate_type",
            "rate_value",
            "effective_date",
            "ingestion_timestamp",
            "currency",
            "source_url",
            "updated_at",
        ]


class RateIngestSerializer(serializers.Serializer):
    """
    Write-path serializer for POST /rates/ingest.

    Accepts raw provider/rate_type strings (not numeric FK ids) because
    the caller is typically a data source integration, not a frontend
    that already has Provider objects loaded — matching the shape of
    the bulk Parquet ingestion path.
    """

    provider = serializers.CharField(max_length=255, allow_blank=False)
    rate_type = serializers.CharField(max_length=64, allow_blank=False)
    rate_value = serializers.DecimalField(max_digits=10, decimal_places=4)
    effective_date = serializers.DateField()
    currency = serializers.CharField(max_length=8, required=False, allow_blank=True)
    source_url = serializers.URLField(max_length=1024, required=False, allow_null=True)
    raw_response_id = serializers.CharField(max_length=255, required=False, allow_null=True)

    def validate_rate_value(self, value: Decimal) -> Decimal:
        if value < Decimal(str(settings.RATE_VALUE_MIN)) or value > Decimal(str(settings.RATE_VALUE_MAX)):
            raise serializers.ValidationError(
                f"rate_value must be between {settings.RATE_VALUE_MIN} and {settings.RATE_VALUE_MAX}."
            )
        return value

    def create(self, validated_data: dict) -> Rate:
        provider_name = normalize_provider_name(validated_data["provider"])
        rate_type_code = normalize_rate_type_code(validated_data["rate_type"])
        currency = normalize_currency(validated_data.get("currency"))

        provider = Provider.objects.filter(name__iexact=provider_name).first()
        if provider is None:
            provider = Provider.objects.create(name=provider_name)

        rate_type, _ = RateType.objects.get_or_create(code=rate_type_code)

        from django.utils import timezone

        rate, _created = Rate.objects.update_or_create(
            provider=provider,
            rate_type=rate_type,
            effective_date=validated_data["effective_date"],
            defaults={
                "rate_value": validated_data["rate_value"],
                "ingestion_timestamp": timezone.now(),
                "currency": currency,
                "source_url": validated_data.get("source_url"),
                "raw_response_id": validated_data.get("raw_response_id"),
            },
        )
        return rate
