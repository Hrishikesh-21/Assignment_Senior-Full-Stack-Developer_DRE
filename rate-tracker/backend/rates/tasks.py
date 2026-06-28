"""
Celery tasks. Like the management command, this is a thin wrapper —
all real logic lives in rates.services.ingestion_service.run_ingestion,
so the manual and scheduled ingestion paths can never drift apart.
"""
import logging

from celery import shared_task
from django.conf import settings

from rates.models import RawIngestion

logger = logging.getLogger("rates")


@shared_task(
    name="rates.scheduled_ingestion",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def scheduled_ingestion_task(self):
    """
    Triggered by Celery Beat on the interval configured via
    INGESTION_SCHEDULE_MINUTES. Re-ingesting the same source file is
    safe because the underlying service is idempotent (upsert on the
    natural key) — this is not "append more rows every hour", it's
    "re-check the source for changes every hour".
    """
    from rates.services.ingestion_service import run_ingestion

    source_file = settings.INGESTION_SOURCE_FILE
    logger.info("celery.scheduled_ingestion.triggered", extra={"source_file": source_file})

    try:
        ingestion = run_ingestion(source_file)
    except Exception as exc:
        logger.error("celery.scheduled_ingestion.error", exc_info=True)
        raise self.retry(exc=exc)

    if ingestion.status == RawIngestion.Status.FAILED:
        # run_ingestion already logs the failure in detail; re-raise so
        # Celery records this task execution as failed too.
        raise RuntimeError(f"Ingestion #{ingestion.id} failed.")

    return {
        "ingestion_id": ingestion.id,
        "status": ingestion.status,
        "rows_read": ingestion.rows_read,
        "rows_inserted": ingestion.rows_inserted,
        "rows_updated": ingestion.rows_updated,
        "rows_rejected": ingestion.rows_rejected,
    }
