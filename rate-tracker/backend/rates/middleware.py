"""
Slow query detection middleware.

Requirement: log any database query slower than SLOW_QUERY_THRESHOLD_MS.
Implemented as middleware (rather than e.g. a custom DB backend) because
it's the simplest way to get a per-request view of total query time using
Django's built-in `connection.queries` — which is only populated when
DEBUG=True or when explicitly forced, so we toggle query recording around
each request to keep this working regardless of the DEBUG setting.
"""
import logging
import time

from django.db import connection, reset_queries

logger = logging.getLogger("rates")


class SlowQueryLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        threshold_ms = getattr(settings, "SLOW_QUERY_THRESHOLD_MS", 200)

        # Force query logging for this request regardless of DEBUG, then
        # restore the connection's force_debug_cursor flag afterward so we
        # don't change behavior for the rest of the process.
        previous_force_debug = connection.force_debug_cursor
        connection.force_debug_cursor = True
        reset_queries()

        start = time.monotonic()
        response = self.get_response(request)
        total_request_ms = (time.monotonic() - start) * 1000

        for query in connection.queries:
            query_time_ms = float(query.get("time", 0)) * 1000
            if query_time_ms > threshold_ms:
                logger.warning(
                    "db.slow_query",
                    extra={
                        "path": request.path,
                        "method": request.method,
                        "query_time_ms": round(query_time_ms, 2),
                        "sql": query.get("sql", "")[:500],
                    },
                )

        connection.force_debug_cursor = previous_force_debug

        logger.info(
            "http.request_completed",
            extra={
                "path": request.path,
                "method": request.method,
                "status_code": response.status_code,
                "total_request_ms": round(total_request_ms, 2),
                "query_count": len(connection.queries),
            },
        )

        return response
