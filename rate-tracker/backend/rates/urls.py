from django.urls import path

from rates.views import HistoryView, IngestRateView, LatestRatesView

app_name = "rates"

urlpatterns = [
    path("rates/latest", LatestRatesView.as_view(), name="rates-latest"),
    path("rates/history", HistoryView.as_view(), name="rates-history"),
    path("rates/ingest", IngestRateView.as_view(), name="rates-ingest"),
]
