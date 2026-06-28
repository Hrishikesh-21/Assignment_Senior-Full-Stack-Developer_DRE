from rates.services.normalization import (
    normalize_currency,
    normalize_provider_name,
    normalize_rate_type_code,
)


class TestNormalizeProviderName:
    def test_collapses_whitespace(self):
        assert normalize_provider_name("HSBC   Bank") == "Hsbc Bank"

    def test_preserves_all_caps_acronym(self):
        assert normalize_provider_name("HSBC") == "HSBC"

    def test_title_cases_mixed_input(self):
        assert normalize_provider_name("hsbc") == "Hsbc"
        assert normalize_provider_name("Hsbc") == "Hsbc"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_provider_name("  HSBC  ") == "HSBC"


class TestNormalizeRateTypeCode:
    def test_uppercases_and_replaces_spaces(self):
        assert normalize_rate_type_code("mortgage 30y") == "MORTGAGE_30Y"

    def test_idempotent_on_already_normalized_input(self):
        assert normalize_rate_type_code("MORTGAGE_30Y") == "MORTGAGE_30Y"


class TestNormalizeCurrency:
    def test_known_alias_maps_to_iso_code(self):
        assert normalize_currency("usd") == "USD"
        assert normalize_currency("US Dollar") == "USD"
        assert normalize_currency("USD") == "USD"

    def test_unknown_currency_is_uppercased_as_is(self):
        assert normalize_currency("xyz") == "XYZ"

    def test_missing_currency_defaults_to_usd(self):
        assert normalize_currency(None) == "USD"
        assert normalize_currency("") == "USD"
        assert normalize_currency("   ") == "USD"
