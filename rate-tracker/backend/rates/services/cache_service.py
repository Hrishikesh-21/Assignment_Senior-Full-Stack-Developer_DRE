"""
Cache service for /rates/latest.

Strategy (full rationale in DECISIONS.md):
  - Cache keys are granular per (provider, rate_type) combination, not
    one blob for the whole endpoint, so invalidating one provider's rate
    doesn't force every other cached response to be recomputed.
  - Invalidation is event-driven: triggered explicitly after every
    successful ingestion/upsert (POST /rates/ingest, management command,
    Celery task), targeting only the specific keys affected.
  - A TTL is still set as a safety net in case an invalidation call is
    ever missed (e.g. a future code path that writes Rate rows without
    going through this cache service) — defense in depth, not the
    primary correctness mechanism.
"""
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("rates")

CACHE_KEY_PREFIX = "rates:latest"


def build_latest_cache_key(provider_id: int | None, rate_type_id: int | None) -> str:
    provider_part = str(provider_id) if provider_id is not None else "all"
    rate_type_part = str(rate_type_id) if rate_type_id is not None else "all"
    return f"{CACHE_KEY_PREFIX}:{provider_part}:{rate_type_part}"


def get_cached_latest(provider_id: int | None, rate_type_id: int | None):
    key = build_latest_cache_key(provider_id, rate_type_id)
    return cache.get(key)


def set_cached_latest(provider_id: int | None, rate_type_id: int | None, value) -> None:
    key = build_latest_cache_key(provider_id, rate_type_id)
    cache.set(key, value, timeout=settings.RATES_LATEST_CACHE_TTL_SECONDS)


def invalidate_latest_cache(provider_id: int | None = None, rate_type_id: int | None = None) -> None:
    """
    Invalidate the specific (provider, rate_type) key plus the "all"
    aggregate keys that would have included this combination. Called
    after every successful write to Rate.
    """
    keys_to_clear = {
        build_latest_cache_key(provider_id, rate_type_id),
        build_latest_cache_key(provider_id, None),
        build_latest_cache_key(None, rate_type_id),
        build_latest_cache_key(None, None),
    }
    cache.delete_many(list(keys_to_clear))
    logger.info(
        "cache.invalidated",
        extra={"keys": list(keys_to_clear), "provider_id": provider_id, "rate_type_id": rate_type_id},
    )
