"""
Data migration: register the scheduled ingestion task with
django-celery-beat's DatabaseScheduler.

Using a migration (rather than a management command run manually, or
hardcoding the schedule in code) means the periodic task is guaranteed
to exist the moment `docker-compose up` finishes running migrations —
no extra manual step. The interval itself is read from
INGESTION_SCHEDULE_MINUTES so the schedule frequency is configuration,
not a hardcoded value, satisfying the spec's "do not hardcode values"
rule even for operational scheduling concerns.
"""
import os

from django.db import migrations


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    minutes = int(os.environ.get("INGESTION_SCHEDULE_MINUTES", "60"))

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=minutes,
        period="minutes",  # IntervalSchedule.MINUTES constant isn't available on the
                            # historical (migration-state) model returned by apps.get_model()
    )

    PeriodicTask.objects.get_or_create(
        name="Scheduled rate ingestion",
        defaults={
            "task": "rates.scheduled_ingestion",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="Scheduled rate ingestion").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rates", "0001_initial"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
