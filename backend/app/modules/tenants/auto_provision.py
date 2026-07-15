"""Auto-provision a tenant for every company that lacks one.

A background task (started from the app lifespan) that periodically ensures each
company in the ``companies`` table has a dedicated tenant — so a newly-synced or
API-created company automatically gets its isolated VisionTrack tenant without a
manual backfill run (multi-tenant Phase 4). Idempotent.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.companies.models import Company
from app.modules.tenants.provisioning import provision_tenant_for_company

log = get_logger("auto_provision")

DEFAULT_INTERVAL_SEC = 300.0


class AutoProvisioner:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="auto-provision")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._provision_once()
            except Exception as e:
                log.warning("auto_provision.failed", error=str(e))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=DEFAULT_INTERVAL_SEC)
            except asyncio.TimeoutError:
                pass

    async def _provision_once(self) -> None:
        async with AsyncSessionLocal() as db:
            companies = (await db.execute(
                select(Company).where(Company.external_id.is_not(None))
            )).scalars().all()
            created = 0
            for c in companies:
                _tenant, was_created = await provision_tenant_for_company(
                    db, external_company_id=c.external_id, name=c.name,
                    admin_username=c.admin_username,
                )
                if was_created:
                    created += 1
            await db.commit()
            if created:
                log.info("auto_provision.created", tenants=created)


auto_provisioner = AutoProvisioner()
