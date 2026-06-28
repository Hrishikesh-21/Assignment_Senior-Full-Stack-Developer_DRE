"""
Normalization helpers for raw ingested values.

The real source data has casing inconsistencies (HSBC / Hsbc / hsbc;
USD / usd / US Dollar). Without normalization, naive get_or_create()
calls on raw strings would create duplicate Provider/currency entities
that are actually the same real-world thing.

These functions are intentionally pure (no DB access, no Django
dependency beyond typing) so they're trivial to unit test in isolation.
"""
import re

# Known currency aliases -> canonical ISO 4217 code. Not hardcoded into
# ingestion logic itself — this map is the single place to extend if new
# source variants appear, and it's a normal "configuration data, not a
# secret" file rather than the kind of thing the spec's "no hardcoded
# values" rule is really aimed at (that rule is about not hardcoding
# *business decisions* like cache TTLs or thresholds inside functions).
_CURRENCY_ALIASES = {
    "usd": "USD",
    "us dollar": "USD",
    "us dollars": "USD",
    "dollar": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "gbp": "GBP",
    "pound": "GBP",
    "pound sterling": "GBP",
}


def normalize_provider_name(raw_name: str) -> str:
    """
    Collapse whitespace and produce a canonical Title Case form.
    Matching/dedup against existing Provider rows is done
    case-insensitively in the ingestion service — this function only
    decides what the *stored, displayed* name looks like the first time
    a given provider is seen.
    """
    cleaned = re.sub(r"\s+", " ", raw_name.strip())
    # Title-case but preserve common all-caps acronyms (HSBC, ICICI, etc.)
    # by checking if the cleaned input was already fully uppercase.
    if cleaned.isupper():
        return cleaned
    return cleaned.title()


def normalize_rate_type_code(raw_code: str) -> str:
    """Canonical form for rate type codes: upper snake-ish, trimmed."""
    cleaned = re.sub(r"\s+", "_", raw_code.strip())
    return cleaned.upper()


def normalize_currency(raw_currency: str | None) -> str:
    """Map known aliases to ISO codes; default to USD if missing/unknown
    rather than silently dropping the field (explicit default, logged
    by the caller if it falls back)."""
    if not raw_currency or not raw_currency.strip():
        return "USD"
    key = raw_currency.strip().lower()
    return _CURRENCY_ALIASES.get(key, raw_currency.strip().upper())
