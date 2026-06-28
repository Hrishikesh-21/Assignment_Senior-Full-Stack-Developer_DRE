"""
Structured JSON logging.

The spec requires JSON logs (not print statements, not plain-text log
lines) so that ingestion events, API failures, and cache invalidations
can be parsed by a log aggregator (CloudWatch, Datadog, ELK, etc.) in a
real deployment. This formatter converts every LogRecord into a single
JSON line.

Application code should never call logger.info("some string") with
business data baked into the string — instead it should pass structured
context via the `extra` kwarg, e.g.:

    logger.info("ingestion.completed", extra={
        "rows_inserted": 100,
        "source_file": "rates_seed.parquet",
    })

so that the resulting JSON line has rows_inserted and source_file as
real, queryable fields rather than text buried in a message string.
"""
import json
import logging
from datetime import datetime, timezone

# Standard LogRecord attributes we don't want to re-dump into the
# "extra" section of the JSON output, since they already have a
# dedicated top-level key (or aren't useful in this context).
_RESERVED_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
}


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Pull in any structured fields passed via `extra={...}`.
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_")
        }
        if extras:
            payload.update(extras)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)
