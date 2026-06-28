"""
RawIngestion — audit trail for every ingestion run (management command,
Celery scheduled task, or otherwise), so ingestion is auditable and
replayable per the spec's requirement.
"""
from django.db import models


class RawIngestion(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        PARTIAL = "PARTIAL", "Partial (some rows rejected)"
        FAILED = "FAILED", "Failed"

    source_file = models.CharField(max_length=512)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )

    rows_read = models.IntegerField(default=0)
    rows_inserted = models.IntegerField(default=0)
    rows_updated = models.IntegerField(default=0)
    rows_rejected = models.IntegerField(default=0)

    # Structured, not a stack-trace dump: a list of {reason, count, sample}
    # objects so the audit log stays queryable and never leaks internals.
    error_summary = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Ingestion[{self.id}] {self.source_file} ({self.status})"

    def mark_finished(self, status: str) -> None:
        from django.utils import timezone

        self.status = status
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "finished_at"])
