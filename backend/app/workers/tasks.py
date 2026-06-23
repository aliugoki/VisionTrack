"""Background tasks executed by Celery workers.

Tasks here are SHORT (target < 5 seconds). Anything longer should be
broken into a chain or moved to a dedicated AI worker process.

Async coordination:
  Celery is sync by default. Our DB access and HTTP calls are async.
  We bridge by spinning up an asyncio loop per task via asyncio.run().
  This is slightly wasteful (one event loop per invocation) but avoids
  pulling in celery-async or making the task code dual-mode.
"""

import asyncio

# Force-load every ORM model so SQLAlchemy can resolve string-referenced
# relationships (Camera.site → Site, etc.) when this worker process boots.
# Without this, the worker only sees models reachable from `run_health_check`'s
# import graph, and any mapper with a forward-reference to a model not in that
# graph fails with "expression 'Site' failed to locate a name". One import,
# whole registry resolved.
from app.core import models as _models  # noqa: F401

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.cameras.health import run_health_check
from app.workers.celery_app import celery_app

log = get_logger("workers.tasks")


@celery_app.task(name="vt.cameras.check_health", bind=True)
def check_camera_health(self):
    """Probe MediaMTX and reconcile camera status into the DB.

    Runs every 30 seconds via the beat schedule. Idempotent — safe to
    re-run if a worker crashes mid-execution.
    """
    try:
        counts = asyncio.run(_run())
        log.info("camera_health.completed", task_id=self.request.id, **counts)
        return counts
    except Exception as e:
        # Don't let one bad check kill the beat schedule; log and move on.
        log.warning(
            "camera_health.failed", task_id=self.request.id, error=str(e)
        )
        return {"error": str(e)}


async def _run() -> dict[str, int]:
    """The actual async health-check workflow."""
    async with AsyncSessionLocal() as db:
        return await run_health_check(db)
