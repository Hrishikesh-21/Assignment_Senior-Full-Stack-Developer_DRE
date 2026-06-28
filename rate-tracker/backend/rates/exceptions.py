"""
Custom exceptions and a structured DRF exception handler.

Requirement from the spec: "Never return generic HTTP 500" and "never
expose stack traces" on the public API. DRF's default exception handler
already does a reasonable job for APIException subclasses (404, 403,
validation errors), but any *unexpected* exception (a bug, a DB hiccup)
would otherwise bubble up as Django's default 500 HTML error page in
production, or a raw traceback in DEBUG mode.

This handler:
  1. Lets DRF handle its own known exception types normally (so
     ValidationError still returns field-level errors, not a generic
     message).
  2. Catches anything else, logs the real exception server-side with
     full detail, and returns a generic structured JSON error to the
     client — never the actual exception message or traceback.
"""
import logging
import uuid

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_exception_handler

logger = logging.getLogger("rates")


class IngestionValidationError(Exception):
    """Raised when an ingested record fails business-rule validation
    (as opposed to serializer-level field validation)."""


def structured_exception_handler(exc, context):
    response = drf_default_exception_handler(exc, context)

    if response is not None:
        # DRF already produced a well-formed error response (e.g. 400
        # validation errors, 401/403 auth errors, 404). Wrap it in a
        # consistent envelope so API consumers always see the same shape.
        response.data = {
            "error": True,
            "detail": response.data,
        }
        return response

    # Anything else is unexpected: log full detail server-side, return
    # only a generic message + correlation id to the client.
    error_id = str(uuid.uuid4())
    request = context.get("request")
    logger.error(
        "api.unhandled_exception",
        extra={
            "error_id": error_id,
            "path": getattr(request, "path", None),
            "method": getattr(request, "method", None),
            "exception_type": type(exc).__name__,
        },
        exc_info=True,
    )

    return Response(
        {
            "error": True,
            "detail": "An unexpected error occurred. Please try again or contact support.",
            "error_id": error_id,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
