"""Platform (cross-tenant) service — list / enter / lifecycle for tenants.

Only reachable by platform admins. "Entering" a tenant mints a token for that
tenant's admin user (impersonation) — reusing the normal auth path so tenant
scoping is unchanged and there is no cross-tenant leakage surface. Lifecycle
(suspend / edit / delete) is platform-admin only, with guards.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.cameras.models import Camera
from app.modules.employees.models import Employee
from app.modules.platform.schemas import PlatformTenantUpdate
from app.modules.tenants.models import Tenant
from app.modules.users.models import User


async def list_all_tenants(db: AsyncSession) -> dict:
    tenants = (await db.execute(select(Tenant).order_by(Tenant.name))).scalars().all()

    emp = dict((await db.execute(
        select(Employee.tenant_id, func.count()).group_by(Employee.tenant_id)
    )).all())
    cam = dict((await db.execute(
        select(Camera.tenant_id, func.count()).group_by(Camera.tenant_id)
    )).all())
    usr = dict((await db.execute(
        select(User.tenant_id, func.count()).group_by(User.tenant_id)
    )).all())

    rows = [{
        "id": t.id, "name": t.name, "subdomain": t.subdomain,
        "external_company_id": t.external_company_id, "plan": t.plan,
        "timezone": t.timezone, "recording_retention_days": t.recording_retention_days,
        "is_active": t.is_active,
        "employee_count": emp.get(t.id, 0), "camera_count": cam.get(t.id, 0),
        "user_count": usr.get(t.id, 0),
    } for t in tenants]
    return {"total": len(rows), "rows": rows}


async def resolve_tenant(db: AsyncSession, tenant_id: UUID) -> Tenant:
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


async def find_tenant_admin(db: AsyncSession, tenant_id: UUID) -> User:
    """Pick the user to impersonate when entering a tenant: a Tenant-Admin-role
    user, else any active user. 409 if the tenant is empty."""
    users = (await db.execute(
        select(User)
        .where(User.tenant_id == tenant_id, User.is_active.is_(True))
        .options(selectinload(User.roles))
        .order_by(User.created_at)
    )).scalars().all()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This tenant has no active user to enter as.",
        )
    for u in users:
        if any(r.name == "Tenant Admin" for r in u.roles):
            return u
    return users[0]


async def update_tenant(
    db: AsyncSession, tenant_id: UUID, payload: PlatformTenantUpdate
) -> Tenant:
    tenant = await resolve_tenant(db, tenant_id)
    if payload.name is not None:
        tenant.name = payload.name
    if payload.is_active is not None:
        tenant.is_active = payload.is_active
    if payload.plan is not None:
        tenant.plan = payload.plan
    if payload.timezone is not None:
        tenant.timezone = payload.timezone
    if payload.recording_retention_days is not None:
        tenant.recording_retention_days = payload.recording_retention_days
    await db.flush()
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def delete_tenant(db: AsyncSession, tenant_id: UUID, *, requester_tenant_id: UUID) -> None:
    """Cascade-delete a tenant and all its data. Guards: not your own home tenant,
    and it must be suspended first (safety for a destructive op)."""
    tenant = await resolve_tenant(db, tenant_id)
    if tenant_id == requester_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't delete the tenant you're signed in from.",
        )
    if tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Suspend the tenant before deleting it.",
        )
    # track_points is a TimescaleDB hypertable with no FK — delete explicitly;
    # every other tenant-scoped table has ON DELETE CASCADE, so dropping the
    # tenant row removes them.
    await db.execute(text("DELETE FROM track_points WHERE tenant_id = :tid"), {"tid": str(tenant_id)})
    await db.delete(tenant)
    await db.commit()
