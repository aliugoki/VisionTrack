"""Tenant HTTP routes.

Endpoints (all return the CURRENT tenant only — the tenant of the
authenticated user. No cross-tenant access):

  GET   /tenants/me   — view current tenant settings
  PATCH /tenants/me   — update name, timezone, retention, settings

Why /me instead of /{id}:
  Tenant boundary is enforced at JWT validation. A request to a
  different tenant's id would either return 403 or be silently filtered.
  Making the URL /me removes the need to even surface the tenant_id
  to the client, and prevents accidental wrong-tenant requests in
  the frontend.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission, get_current_user
from app.core.permissions import TENANT_READ, TENANT_UPDATE
from app.modules.tenants.schemas import TenantRead, TenantUpdate
from app.modules.tenants.service import get_tenant, update_tenant
from app.modules.users.models import User


router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/me", response_model=TenantRead)
async def read_my_tenant(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(RequirePermission(TENANT_READ)),
) -> TenantRead:
    """Return the authenticated user's tenant."""
    tenant = await get_tenant(db, current_user.tenant_id)
    if tenant is None:
        # Should be impossible — JWT validity implies tenant exists —
        # but defensive in case of soft-delete edge cases.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return TenantRead.model_validate(tenant)


@router.patch("/me", response_model=TenantRead)
async def update_my_tenant(
    payload: TenantUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = Depends(RequirePermission(TENANT_UPDATE)),
) -> TenantRead:
    """Update tenant settings. PATCH semantics: only sets provided fields."""
    tenant = await get_tenant(db, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    updated = await update_tenant(db, tenant, payload)
    return TenantRead.model_validate(updated)
