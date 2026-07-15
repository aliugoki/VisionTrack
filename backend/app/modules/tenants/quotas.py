"""Per-tenant quotas (multi-tenant Phase 5).

Quotas live in ``tenant.settings`` (JSONB) and are set by a platform admin via
``PATCH /platform/tenants/{id}``. A quota of 0 / unset means unlimited, so
existing tenants are unaffected until a limit is applied.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cameras.models import Camera
from app.modules.tenants.models import Tenant


async def enforce_camera_quota(db: AsyncSession, tenant_id: UUID) -> None:
    """Raise 409 if the tenant is at its camera limit."""
    settings = (await db.execute(
        select(Tenant.settings).where(Tenant.id == tenant_id)
    )).scalar_one_or_none() or {}
    limit = settings.get("max_cameras")
    if not limit:  # 0 / None / missing -> unlimited
        return
    count = (await db.execute(
        select(func.count()).select_from(Camera).where(Camera.tenant_id == tenant_id)
    )).scalar_one()
    if count >= int(limit):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Camera limit reached for this tenant ({limit}).",
        )
