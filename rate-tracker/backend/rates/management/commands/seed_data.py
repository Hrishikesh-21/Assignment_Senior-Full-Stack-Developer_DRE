"""
python manage.py seed_data --file /app/data/rates_seed.parquet

Thin wrapper around IngestionService — contains no business logic of its
own, so the same code path is exercised whether ingestion is triggered
manually or by the Celery Beat schedule.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from rates.models import RawIngestion
from rates.services.ingestion_service import run_ingestion


class Command(BaseCommand):
    help = "Ingest rate data from a Parquet file into PostgreSQL (idempotent, batched)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Path to the Parquet file to ingest. Defaults to settings.INGESTION_SOURCE_FILE.",
        )

    def handle(self, *args, **options):
        source_file = options["file"] or settings.INGESTION_SOURCE_FILE

        self.stdout.write(f"Starting ingestion from {source_file} ...")

        try:
            ingestion: RawIngestion = run_ingestion(source_file)
        except FileNotFoundError as exc:
            raise CommandError(f"Source file not found: {source_file}") from exc
        except Exception as exc:
            raise CommandError(f"Ingestion failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Ingestion #{ingestion.id} finished with status={ingestion.status}. "
                f"read={ingestion.rows_read} inserted={ingestion.rows_inserted} "
                f"updated={ingestion.rows_updated} rejected={ingestion.rows_rejected}"
            )
        )

        if ingestion.status == RawIngestion.Status.FAILED:
            raise CommandError(f"Ingestion #{ingestion.id} failed. See logs for details.")
