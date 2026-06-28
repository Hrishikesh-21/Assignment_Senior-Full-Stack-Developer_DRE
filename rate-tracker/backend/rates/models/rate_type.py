"""
RateType lookup table (e.g. MORTGAGE_30Y, SAVINGS_APY).

Normalized for the same reasons as Provider: small, stable set of values
that would otherwise be duplicated as free text across ~1M rate rows.
"""
from django.db import models


class RateType(models.Model):
    code = models.CharField(
        max_length=64,
        unique=True,
        help_text="Canonical rate type code, e.g. 'MORTGAGE_30Y'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code
