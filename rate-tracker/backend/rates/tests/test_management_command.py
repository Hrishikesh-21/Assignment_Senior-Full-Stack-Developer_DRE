import datetime
from io import StringIO

import pandas as pd
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from rates.models import Rate


def _write_parquet(tmp_path, rows, filename="seed.parquet"):
    df = pd.DataFrame(rows)
    path = tmp_path / filename
    df.to_parquet(path, engine="pyarrow")
    return str(path)


@pytest.mark.django_db
class TestSeedDataCommand:
    def test_command_ingests_file_successfully(self, tmp_path):
        rows = [
            {"provider": "HSBC", "rate_type": "MORTGAGE_30Y", "rate_value": 6.75,
             "effective_date": datetime.date(2026, 1, 1), "ingestion_ts": datetime.datetime(2026, 1, 1, 9, 0)},
        ]
        path = _write_parquet(tmp_path, rows)

        out = StringIO()
        call_command("seed_data", f"--file={path}", stdout=out)

        assert Rate.objects.count() == 1
        assert "finished with status=SUCCESS" in out.getvalue()

    def test_command_raises_clear_error_on_missing_file(self):
        with pytest.raises(CommandError, match="Source file not found"):
            call_command("seed_data", "--file=/nonexistent/file.parquet")

    def test_command_uses_settings_default_when_no_file_arg(self, settings, tmp_path):
        rows = [
            {"provider": "HSBC", "rate_type": "MORTGAGE_30Y", "rate_value": 6.75,
             "effective_date": datetime.date(2026, 1, 1), "ingestion_ts": datetime.datetime(2026, 1, 1, 9, 0)},
        ]
        path = _write_parquet(tmp_path, rows)
        settings.INGESTION_SOURCE_FILE = path

        call_command("seed_data")

        assert Rate.objects.count() == 1
