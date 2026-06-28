"""
Fail-fast environment variable validation.

Runs at container boot (before Django even attempts to import settings that
depend on these variables). The goal: if a required variable is missing,
the developer sees ONE clear error message immediately, rather than a deep
Django traceback five layers into settings.py or a silent fallback to a
wrong default.
"""
import os
import sys

REQUIRED_VARS = [
    "DJANGO_SECRET_KEY",
    "DJANGO_DEBUG",
    "DJANGO_ALLOWED_HOSTS",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "REDIS_HOST",
    "REDIS_PORT",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "INGESTION_API_TOKEN",
    "INGESTION_SCHEDULE_MINUTES",
]


def validate() -> None:
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        sys.stderr.write(
            "\n"
            "=========================================================\n"
            " STARTUP FAILED: missing required environment variable(s)\n"
            "=========================================================\n"
            f" Missing: {', '.join(missing)}\n\n"
            " Copy .env.example to .env and fill in every value before\n"
            " running docker-compose up.\n"
            "=========================================================\n"
        )
        sys.exit(1)
    print("[validate_env] All required environment variables are present.")


if __name__ == "__main__":
    validate()
