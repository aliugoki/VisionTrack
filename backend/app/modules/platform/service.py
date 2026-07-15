"""Platform (cross-tenant) service — list all tenants + enter (impersonate) one.

Only reachable by platform admins. "Entering" a tenant mints a token for that
tenant's admin user (impersonation) — deliberately reusing the normal auth path
(token -> sub -> user.tenant_id) so tenant scoping is unchanged and there is no
cross-tenant leakage surface.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.cameras.models import Camera
from app.modules.employees.models import Employee
from app.modules.roles.models import Role
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

    rows = [{
        "id": t.id, "name": t.name, "subdomain": t.subdomain,
        "external_company_id": t.external_company_id, "is_active": t.is_active,
        "employee_count": emp.get(t.id, 0), "camera_count": cam.get(t.id, 0),
    } for t in tenants]
    return {"total": len(rows), "rows": rows}


async def find_tenant_admin(db: AsyncSession, tenant_id: UUID) -> User:
    """Pick the user to impersonate when entering a tenant: a Tenant-Admin-role
    user, else any active user. 404 if the tenant is empty."""
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


async def resolve_tenant(db: AsyncSession, tenant_id: UUID) -> Tenant:
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant
