from unittest.mock import MagicMock, patch

import pytest

from rates.models import RawIngestion
from rates.tasks import scheduled_ingestion_task


@pytest.mark.django_db
class TestScheduledIngestionTask:
    @patch("rates.services.ingestion_service.run_ingestion")
    def test_successful_ingestion_returns_summary(self, mock_run_ingestion):
        mock_ingestion = MagicMock()
        mock_ingestion.id = 1
        mock_ingestion.status = RawIngestion.Status.SUCCESS
        mock_ingestion.rows_read = 100
        mock_ingestion.rows_inserted = 90
        mock_ingestion.rows_updated = 10
        mock_ingestion.rows_rejected = 0
        mock_run_ingestion.return_value = mock_ingestion

        result = scheduled_ingestion_task.apply().result

        assert result["status"] == RawIngestion.Status.SUCCESS
        assert result["rows_inserted"] == 90

    @patch("rates.services.ingestion_service.run_ingestion")
    def test_failed_ingestion_raises_for_celery_retry_tracking(self, mock_run_ingestion):
        mock_ingestion = MagicMock()
        mock_ingestion.id = 2
        mock_ingestion.status = RawIngestion.Status.FAILED
        mock_run_ingestion.return_value = mock_ingestion

        result = scheduled_ingestion_task.apply()

        assert result.failed()

    @patch("rates.services.ingestion_service.run_ingestion")
    def test_exception_during_ingestion_triggers_retry_path(self, mock_run_ingestion):
        mock_run_ingestion.side_effect = ValueError("source file corrupt")

        result = scheduled_ingestion_task.apply()

        # CELERY_TASK_ALWAYS_EAGER mode surfaces retry() as a raised
        # exception rather than an actual requeue; either way the task
        # must not silently swallow the error.
        assert result.failed()
