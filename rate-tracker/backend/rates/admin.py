from django.contrib import admin

from .models import Provider, Rate, RateType, RawIngestion


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "created_at"]
    search_fields = ["name"]


@admin.register(RateType)
class RateTypeAdmin(admin.ModelAdmin):
    list_display = ["id", "code", "created_at"]
    search_fields = ["code"]


@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = [
        "id", "provider", "rate_type", "rate_value",
        "effective_date", "ingestion_timestamp", "currency",
    ]
    list_filter = ["provider", "rate_type", "currency"]
    search_fields = ["provider__name", "rate_type__code", "raw_response_id"]
    date_hierarchy = "effective_date"


@admin.register(RawIngestion)
class RawIngestionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "source_file", "status", "started_at", "finished_at",
        "rows_read", "rows_inserted", "rows_updated", "rows_rejected",
    ]
    list_filter = ["status"]
    readonly_fields = [f.name for f in RawIngestion._meta.fields]
