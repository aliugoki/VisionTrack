"""Celery application — background workers and scheduled tasks.

We use Redis as both broker and result backend. The same Redis instance
the AI worker uses for its event streams (different DB number) keeps the
infrastructure simple.

Running it:
  # Worker that executes tasks
  celery -A app.workers.celery_app worker --loglevel=info --concurrency=2

  # Beat scheduler that fires periodic tasks
  celery -A app.workers.celery_app beat --loglevel=info

In docker-compose these are two separate services (`worker` and `beat`).

Task discovery: we explicitly import `app.workers.tasks` here so that
@celery_app.task decorators run at module load time and tasks register.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "visiontrack",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks",
        "app.workers.alerts_tasks",
        "app.workers.retention_tasks",
    ],
)

celery_app.conf.update(
    # Time zone matches first tenant's default site. In multi-tenant
    # production each task should resolve its own tenant timezone.
    timezone="Asia/Karachi",
    enable_utc=True,

    # Acknowledge tasks only AFTER they complete. If a worker crashes
    # mid-task the broker re-queues it. Safe because our tasks are
    # idempotent (health check is just a status reconcile).
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Result expiry — we mostly don't read results, but if a debugger
    # queries them, expire after an hour.
    result_expires=3600,

    # Periodic schedule. Easy to add new entries here as more background
    # tasks come online (recording retention, alert dispatch, etc.).
    beat_schedule={
        "check-camera-health-every-30s": {
            "task": "vt.cameras.check_health",
            "schedule": 30.0,  # seconds
            "options": {"expires": 25},  # if a check is older than 25s, drop it
        },
        # Zone rule evaluation. 5-second cadence balances alert latency
        # vs CPU/DB cost. With ~10 zones per plan and ~3 rules per zone,
        # one tick processes ~30 rules — well within a few hundred ms.
        # `expires=4` means if beat falls behind by 4s we drop the
        # delayed tick rather than queue duplicate work.
        "evaluate-alert-rules-every-5s": {
            "task": "vt.alerts.evaluate",
            "schedule": 5.0,
            "options": {"expires": 4},
        },
        # Recording retention sweep. Runs at 03:00 server tz (Asia/Karachi)
        # — off-peak so we don't compete with daytime stream writes. The
        # task is bounded (max 5000 deletions per tenant per run) so even
        # a sudden policy change can't monopolize the DB.
        "recording-retention-sweep-nightly": {
            "task": "vt.recordings.retention_sweep",
            "schedule": crontab(hour=3, minute=0),
            "options": {"expires": 3600},  # if beat misses by an hour, skip
        },
    },
)
