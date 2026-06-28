"""
Celery application setup.

The Celery app is created here (not in __init__.py directly) following
the standard Django+Celery pattern so that `from config.celery import app`
works cleanly from tasks.py and from the celery worker/beat CLI entrypoints
in docker-compose.yml.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")

app = Celery("rate_tracker")

# Pull CELERY_* settings from Django settings (CELERY_BROKER_URL etc.)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every installed app (i.e. rates/tasks.py)
app.autodiscover_tasks()
