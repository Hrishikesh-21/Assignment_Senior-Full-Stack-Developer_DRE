"""
Provider lookup table.

Normalized out of Rate (rather than storing provider name as a raw string
on every row) because:
  1. The source data has real casing inconsistency (HSBC / Hsbc / hsbc are
     the same institution) — a lookup table with a canonical name plus
     case-insensitive resolution is the only clean way to dedupe that.
  2. The provider set is small (tens, not millions) relative to the rates
     table, so normalizing saves significant storage and keeps indexes
     smaller on the large table.
  3. Gives a natural place to add provider metadata later (region,
     is_active, logo_url) without touching the rates schema.
"""
from django.db import models


class Provider(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Canonical display name, e.g. 'HSBC'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
