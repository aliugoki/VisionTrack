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
from app.modules.auth.router import _issue_tokens
from app.modules.auth.schemas import TokenPair
from app.modules.platform.schemas import PlatformTenantList
from app.modules.platform.service import (
    find_tenant_admin,
    list_all_tenants,
    resolve_tenant,
)
from app.modules.users.models import User

router = APIRouter(prefix="/platform", tags=["platform"])


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
    _admin: User = Depends(require_platform_admin),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> TokenPair:
    """Enter a tenant: returns a token pair scoped to that tenant (impersonating
    its admin). The caller keeps their platform token to switch again / exit."""
    await resolve_tenant(db, tenant_id)
    admin = await find_tenant_admin(db, tenant_id)
    return await _issue_tokens(db, admin, touch_last_login=False)
