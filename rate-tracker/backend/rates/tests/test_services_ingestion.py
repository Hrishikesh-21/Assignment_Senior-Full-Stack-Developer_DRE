import datetime
from decimal import Decimal

import pandas as pd
import pytest

from rates.models import Provider, Rate, RateType, RawIngestion
from rates.services.ingestion_service import run_ingestion


def _write_parquet(tmp_path, rows: list[dict], filename: str = "test_seed.parquet"):
    df = pd.DataFrame(rows)
    path = tmp_path / filename
    df.to_parquet(path, engine="pyarrow")
    return str(path)


@pytest.mark.django_db
class TestIngestionService:
    def test_basic_ingestion_creates_rate_and_dimensions(self, tmp_path):
        rows = [
            {
                "provider": "HSBC",
                "rate_type": "MORTGAGE_30Y",
                "rate_value": 6.75,
                "effective_date": datetime.date(2026, 1, 1),
                "ingestion_ts": datetime.datetime(2026, 1, 1, 9, 0),
                "currency": "USD",
                "source_url": "https://example.com/hsbc",
                "raw_response_id": "abc-1",
            }
        ]
        path = _write_parquet(tmp_path, rows)

        ingestion = run_ingestion(path)

        assert ingestion.status == RawIngestion.Status.SUCCESS
        assert ingestion.rows_read == 1
        assert ingestion.rows_inserted == 1
        assert Rate.objects.count() == 1
        assert Provider.objects.filter(name="HSBC").exists()
        assert RateType.objects.filter(code="MORTGAGE_30Y").exists()

    def test_provider_casing_variants_resolve_to_one_provider(self, tmp_path):
        rows = [
            {"provider": "HSBC", "rate_type": "SAVINGS", "rate_value": 1.0,
             "effective_date": datetime.date(2026, 1, 1), "ingestion_ts": datetime.datetime(2026, 1, 1, 9, 0)},
            {"provider": "hsbc", "rate_type": "SAVINGS", "rate_value": 1.1,
             "effective_date": datetime.date(2026, 1, 2), "ingestion_ts": datetime.datetime(2026, 1, 2, 9, 0)},
            {"provider": "Hsbc", "rate_type": "SAVINGS", "rate_value": 1.2,
             "effective_date": datetime.date(2026, 1, 3), "ingestion_ts": datetime.datetime(2026, 1, 3, 9, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        run_ingestion(path)

        assert Provider.objects.count() == 1
        assert Rate.objects.count() == 3

    def test_duplicate_natural_key_keeps_latest_ingestion_ts(self, tmp_path):
        rows = [
            {"provider": "PNC", "rate_type": "ARM_5Y", "rate_value": 5.0,
             "effective_date": datetime.date(2026, 1, 4), "ingestion_ts": datetime.datetime(2026, 1, 4, 8, 0)},
            {"provider": "PNC", "rate_type": "ARM_5Y", "rate_value": 5.5,
             "effective_date": datetime.date(2026, 1, 4), "ingestion_ts": datetime.datetime(2026, 1, 4, 20, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        run_ingestion(path)

        assert Rate.objects.count() == 1
        rate = Rate.objects.first()
        assert rate.rate_value == Decimal("5.5")

    def test_null_rate_value_is_rejected_not_crashed(self, tmp_path):
        rows = [
            {"provider": "PNC", "rate_type": "ARM_5Y", "rate_value": None,
             "effective_date": datetime.date(2026, 1, 4), "ingestion_ts": datetime.datetime(2026, 1, 4, 8, 0)},
            {"provider": "PNC", "rate_type": "ARM_5Y", "rate_value": 5.5,
             "effective_date": datetime.date(2026, 1, 5), "ingestion_ts": datetime.datetime(2026, 1, 5, 8, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        ingestion = run_ingestion(path)

        assert ingestion.status == RawIngestion.Status.PARTIAL
        assert ingestion.rows_rejected == 1
        assert ingestion.rows_inserted == 1
        assert ingestion.error_summary is not None
        assert "null_rate_value" in ingestion.error_summary

    def test_out_of_range_rate_value_is_rejected(self, tmp_path):
        rows = [
            {"provider": "PNC", "rate_type": "ARM_5Y", "rate_value": -3.0,
             "effective_date": datetime.date(2026, 1, 4), "ingestion_ts": datetime.datetime(2026, 1, 4, 8, 0)},
            {"provider": "PNC", "rate_type": "ARM_5Y", "rate_value": 999.0,
             "effective_date": datetime.date(2026, 1, 5), "ingestion_ts": datetime.datetime(2026, 1, 5, 8, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        ingestion = run_ingestion(path)

        assert ingestion.rows_rejected == 2
        assert ingestion.rows_inserted == 0

    def test_missing_provider_is_rejected(self, tmp_path):
        rows = [
            {"provider": "", "rate_type": "ARM_5Y", "rate_value": 5.0,
             "effective_date": datetime.date(2026, 1, 4), "ingestion_ts": datetime.datetime(2026, 1, 4, 8, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        ingestion = run_ingestion(path)

        assert ingestion.rows_rejected == 1
        assert ingestion.rows_inserted == 0

    def test_ingestion_is_idempotent_on_rerun(self, tmp_path):
        rows = [
            {"provider": "HSBC", "rate_type": "MORTGAGE_30Y", "rate_value": 6.75,
             "effective_date": datetime.date(2026, 1, 1), "ingestion_ts": datetime.datetime(2026, 1, 1, 9, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        run_ingestion(path)
        second = run_ingestion(path)

        assert Rate.objects.count() == 1
        assert second.rows_updated == 1
        assert second.rows_inserted == 0

    def test_rerun_with_changed_value_updates_existing_row(self, tmp_path):
        rows_v1 = [
            {"provider": "HSBC", "rate_type": "MORTGAGE_30Y", "rate_value": 6.75,
             "effective_date": datetime.date(2026, 1, 1), "ingestion_ts": datetime.datetime(2026, 1, 1, 9, 0)},
        ]
        path_v1 = _write_parquet(tmp_path, rows_v1, "v1.parquet")
        run_ingestion(path_v1)

        rows_v2 = [
            {"provider": "HSBC", "rate_type": "MORTGAGE_30Y", "rate_value": 7.10,
             "effective_date": datetime.date(2026, 1, 1), "ingestion_ts": datetime.datetime(2026, 1, 1, 18, 0)},
        ]
        path_v2 = _write_parquet(tmp_path, rows_v2, "v2.parquet")
        ingestion = run_ingestion(path_v2)

        assert Rate.objects.count() == 1
        assert Rate.objects.first().rate_value == Decimal("7.10")
        assert ingestion.rows_updated == 1

    def test_records_raw_ingestion_audit_row(self, tmp_path):
        rows = [
            {"provider": "HSBC", "rate_type": "MORTGAGE_30Y", "rate_value": 6.75,
             "effective_date": datetime.date(2026, 1, 1), "ingestion_ts": datetime.datetime(2026, 1, 1, 9, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        ingestion = run_ingestion(path)

        stored = RawIngestion.objects.get(id=ingestion.id)
        assert stored.source_file == path
        assert stored.started_at is not None
        assert stored.finished_at is not None

    def test_missing_file_raises_clear_error(self):
        with pytest.raises(Exception):
            run_ingestion("/nonexistent/path/file.parquet")
