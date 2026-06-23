"""Recording retention sweep — nightly Celery task.

For each tenant, deletes Recording rows older than
`tenant.recording_retention_days`. Also unlinks the on-disk file when
it still exists (MediaMTX's own recordDeleteAfter may have already
swept it; that's fine, we tolerate ENOENT).

Cadence:
  Registered in celery_app.beat_schedule to run nightly at 03:00
  (server tz = Asia/Karachi). Off-peak so sweep IO doesn't compete
  with daytime stream writes.

Idempotency:
  Each tenant gets its own session. If the task crashes partway,
  retry-on-failure picks up where it left off — we always delete the
  OLDEST rows first, so a re-run finds the same set minus whatever
  the previous attempt already deleted.

Safety rails:
  - Hard cap of 5,000 deletions per tenant per run, to avoid a runaway
    sweep monopolizing the DB if retention_days was dropped from 365
    to 7 in a single config change.
  - File deletes are best-effort; we never block on filesystem failure.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.recordings.models import Recording
from app.modules.tenants.models import Tenant
from app.workers.celery_app import celery_app


log = get_logger("recordings.retention")

# Hard cap on rows deleted per tenant per run (safety rail)
MAX_DELETIONS_PER_TENANT_PER_RUN = 5000


@celery_app.task(name="vt.recordings.retention_sweep", bind=True)
def retention_sweep_task(self) -> dict[str, Any]:
    """Sync entrypoint Celery calls. Defers to async impl."""
    try:
        return asyncio.run(_sweep_all_tenants())
    except Exception as e:
        log.warning(
            "retention.sweep_failed",
            task_id=self.request.id,
            error=str(e),
        )
        return {"error": str(e)}


async def _sweep_all_tenants() -> dict[str, Any]:
    """Iterate every active tenant + run a sweep pass for each."""
    summary: dict[str, Any] = {
        "tenants_processed": 0,
        "rows_deleted_total": 0,
        "files_unlinked_total": 0,
        "files_missing_total": 0,
        "per_tenant": [],
    }

    async with AsyncSessionLocal() as db:
        tenants = list(
            (await db.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )

    for tenant in tenants:
        per_tenant = await _sweep_tenant(tenant)
        summary["tenants_processed"] += 1
        summary["rows_deleted_total"] += per_tenant["rows_deleted"]
        summary["files_unlinked_total"] += per_tenant["files_unlinked"]
        summary["files_missing_total"] += per_tenant["files_missing"]
        summary["per_tenant"].append(per_tenant)

    log.info("retention.sweep_complete", **{
        k: v for k, v in summary.items() if k != "per_tenant"
    })
    return summary


async def _sweep_tenant(tenant: Tenant) -> dict[str, Any]:
    """Sweep one tenant's expired recordings.

    Strategy:
      1. SELECT expired rows + storage_path (limit 5000) — gives us the
         file paths before DELETE so we can unlink them
      2. Best-effort unlink each file
      3. DELETE the rows we just listed (by ID)

    We split SELECT + DELETE because DELETE RETURNING + Python-side file
    unlinks would require a longer-held transaction. The two-step
    approach keeps each DB transaction tiny and acceptable to do under
    asyncpg pool.
    """
    out: dict[str, Any] = {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "retention_days": int(tenant.recording_retention_days),
        "rows_deleted": 0,
        "files_unlinked": 0,
        "files_missing": 0,
    }

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=int(tenant.recording_retention_days)
    )

    async with AsyncSessionLocal() as db:
        # Step 1: select the expired set (id + path)
        sel = (
            select(Recording.id, Recording.storage_path)
            .where(
                Recording.tenant_id == tenant.id,
                Recording.started_at < cutoff,
            )
            .order_by(Recording.started_at.asc())
            .limit(MAX_DELETIONS_PER_TENANT_PER_RUN)
        )
        rows = list((await db.execute(sel)).all())

        if not rows:
            return out

        ids_to_delete = [r.id for r in rows]
        paths_to_unlink = [r.storage_path for r in rows]

        # Step 2: unlink files best-effort
        for p in paths_to_unlink:
            try:
                os.unlink(p)
                out["files_unlinked"] += 1
            except FileNotFoundError:
                # MediaMTX already swept it via recordDeleteAfter, fine
                out["files_missing"] += 1
            except OSError as e:
                log.warning(
                    "retention.unlink_failed",
                    tenant_id=str(tenant.id),
                    path=p,
                    error=str(e),
                )

        # Step 3: delete rows by id
        del_stmt = delete(Recording).where(Recording.id.in_(ids_to_delete))
        result = await db.execute(del_stmt)
        out["rows_deleted"] = result.rowcount or 0
        await db.commit()

    log.info(
        "retention.tenant_swept",
        tenant_id=str(tenant.id),
        retention_days=out["retention_days"],
        rows_deleted=out["rows_deleted"],
        files_unlinked=out["files_unlinked"],
        files_missing=out["files_missing"],
    )
    return out
