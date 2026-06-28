"""
Views — deliberately thin. Each view's job is: parse request params,
call a service, serialize the result, return a response. No business
logic (query construction, cache key building, validation rules) lives
here — see rates/services/ for that.
"""
import logging

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rates.authentication import StaticBearerTokenAuthentication
from rates.models import Provider, RateType
from rates.permissions import HasValidIngestToken
from rates.serializers import RateIngestSerializer, RateReadSerializer
from rates.services.cache_service import (
    get_cached_latest,
    invalidate_latest_cache,
    set_cached_latest,
)
from rates.services.rate_query_service import MAX_HISTORY_PAGE_SIZE, RateQueryService

logger = logging.getLogger("rates")


def _lookup_provider_id(provider_param: str | None) -> int | None:
    if not provider_param:
        return None
    provider = Provider.objects.filter(name__iexact=provider_param).first()
    if provider is None:
        raise ValidationError({"provider": f"Unknown provider '{provider_param}'."})
    return provider.id


def _lookup_rate_type_id(rate_type_param: str | None) -> int | None:
    if not rate_type_param:
        return None
    rate_type = RateType.objects.filter(code__iexact=rate_type_param).first()
    if rate_type is None:
        raise ValidationError({"rate_type": f"Unknown rate_type '{rate_type_param}'."})
    return rate_type.id


def _parse_date_param(param_name: str, raw_value: str | None):
    if not raw_value:
        return None
    from datetime import datetime

    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError({param_name: f"'{raw_value}' is not a valid date. Expected format: YYYY-MM-DD."})


class LatestRatesView(APIView):
    """
    GET /api/rates/latest?provider=&rate_type=

    No authentication required (per spec). Redis-cached with
    event-driven invalidation — see rates/services/cache_service.py.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        provider_param = request.query_params.get("provider")
        rate_type_param = request.query_params.get("rate_type")

        provider_id = _lookup_provider_id(provider_param)
        rate_type_id = _lookup_rate_type_id(rate_type_param)

        cached = get_cached_latest(provider_id, rate_type_id)
        if cached is not None:
            logger.info(
                "cache.hit",
                extra={"endpoint": "rates.latest", "provider_id": provider_id, "rate_type_id": rate_type_id},
            )
            return Response(cached)

        logger.info(
            "cache.miss",
            extra={"endpoint": "rates.latest", "provider_id": provider_id, "rate_type_id": rate_type_id},
        )
        queryset = RateQueryService.get_latest_rates(provider_id=provider_id, rate_type_id=rate_type_id)
        serialized = RateReadSerializer(queryset, many=True).data

        set_cached_latest(provider_id, rate_type_id, serialized)
        return Response(serialized)


class HistoryPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = MAX_HISTORY_PAGE_SIZE  # hard ceiling — "never allow unlimited responses"


class HistoryView(ListAPIView):
    """
    GET /api/rates/history?provider=&rate_type=&from=&to=

    No authentication required (per spec). Always paginated; page size
    is capped server-side regardless of what the client requests.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RateReadSerializer
    pagination_class = HistoryPagination

    def get_queryset(self):
        params = self.request.query_params
        provider_id = _lookup_provider_id(params.get("provider"))
        rate_type_id = _lookup_rate_type_id(params.get("rate_type"))

        date_from = _parse_date_param("from", params.get("from"))
        date_to = _parse_date_param("to", params.get("to"))

        return RateQueryService.get_history(
            provider_id=provider_id,
            rate_type_id=rate_type_id,
            date_from=date_from,
            date_to=date_to,
        )


class IngestRateView(APIView):
    """
    POST /api/rates/ingest

    Bearer-token authenticated. Strictly validates the payload via
    RateIngestSerializer, performs an upsert (so re-posting the same
    provider/rate_type/effective_date corrects rather than duplicates),
    and invalidates only the affected cache keys.

    Never returns a raw 500 / stack trace — unexpected errors are
    caught by rates.exceptions.structured_exception_handler at the DRF
    level; this view only needs to handle the *expected* validation
    failure path itself.
    """

    authentication_classes = [StaticBearerTokenAuthentication]
    permission_classes = [HasValidIngestToken]

    def post(self, request):
        serializer = RateIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rate = serializer.save()

        invalidate_latest_cache(provider_id=rate.provider_id, rate_type_id=rate.rate_type_id)

        logger.info(
            "api.ingest.success",
            extra={
                "provider": rate.provider.name,
                "rate_type": rate.rate_type.code,
                "effective_date": str(rate.effective_date),
            },
        )

        return Response(RateReadSerializer(rate).data, status=status.HTTP_201_CREATED)
