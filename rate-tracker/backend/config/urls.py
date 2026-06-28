from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    """
    Liveness endpoint for Docker healthchecks and uptime monitoring.
    Deliberately has zero dependencies (no DB/Redis check) so it can
    answer instantly even if downstream services are degraded — a
    separate /health/ready/ endpoint would be the place for dependency
    checks if this project needed one.
    """
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path("api/", include("rates.urls")),
]
