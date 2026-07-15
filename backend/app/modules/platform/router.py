"""Platform (cross-tenant) HTTP routes — platform admins only.

  GET  /platform/tenants                  list every tenant (company)
  POST /platform/tenants/{id}/enter       mint a token scoped to that tenant
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.modules.auth.router import _issue_tokens
from app.modules.auth.schemas import TokenPair
from app.modules.platform.schemas import (
    PlatformTenant,
    PlatformTenantList,
    PlatformTenantUpdate,
)
from app.modules.platform.service import (
    delete_tenant,
    find_tenant_admin,
    list_all_tenants,
    resolve_tenant,
    update_tenant,
)
from app.modules.users.models import User

router = APIRouter(prefix="/platform", tags=["platform"])
log = get_logger("platform.audit")


def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    if not getattr(current_user, "is_platform_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required",
        )
    return current_user


@router.get("/tenants", response_model=PlatformTenantList)
async def list_tenants_endpoint(
    _admin: User = Depends(require_platform_admin),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> PlatformTenantList:
    data = await list_all_tenants(db)
    return PlatformTenantList(**data)


@router.post("/tenants/{tenant_id}/enter", response_model=TokenPair)
async def enter_tenant_endpoint(
    tenant_id: UUID,
    admin: User = Depends(require_platform_admin),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> TokenPair:
    """Enter a tenant: returns a token pair scoped to that tenant (impersonating
    its admin). The caller keeps their platform token to switch again / exit."""
    tenant = await resolve_tenant(db, tenant_id)
    tenant_admin = await find_tenant_admin(db, tenant_id)
    # Audit: impersonation attributes later actions to the tenant admin, so record
    # who actually entered which tenant.
    log.info("platform.enter", actor=admin.email, actor_id=str(admin.id),
             tenant_id=str(tenant_id), tenant=tenant.name)
    return await _issue_tokens(db, tenant_admin, touch_last_login=False)


@router.patch("/tenants/{tenant_id}", response_model=PlatformTenant)
async def update_tenant_endpoint(
    tenant_id: UUID,
    payload: PlatformTenantUpdate,
    admin: User = Depends(require_platform_admin),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> PlatformTenant:
    """Update a tenant (suspend/activate, rename, timezone, plan, retention)."""
    tenant = await update_tenant(db, tenant_id, payload)
    log.info("platform.tenant_updated", actor=admin.email, tenant_id=str(tenant_id),
             changes=payload.model_dump(exclude_none=True))
    return PlatformTenant(
        id=tenant.id, name=tenant.name, subdomain=tenant.subdomain,
        external_company_id=tenant.external_company_id, plan=tenant.plan,
        timezone=tenant.timezone, recording_retention_days=tenant.recording_retention_days,
        is_active=tenant.is_active,
        max_cameras=(tenant.settings or {}).get("max_cameras", 0),
    )


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant_endpoint(
    tenant_id: UUID,
    admin: User = Depends(require_platform_admin),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
):
    """Cascade-delete a tenant + all its data (must be suspended first)."""
    await delete_tenant(db, tenant_id, requester_tenant_id=admin.tenant_id)
    log.warning("platform.tenant_deleted", actor=admin.email, actor_id=str(admin.id),
                tenant_id=str(tenant_id))
