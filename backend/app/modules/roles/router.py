"""Roles HTTP routes.

Endpoints:
  GET    /roles/permissions    Public catalog of all permission keys
  GET    /roles                List roles in current tenant
  POST   /roles                Create a custom role
  GET    /roles/{id}           Read one role
  PATCH  /roles/{id}           Update a role (system roles: perms only)
  DELETE /roles/{id}           Delete a custom role
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.deps import RequirePermission, get_current_user
from app.core.permissions import (
    PERMISSION_CATALOG,
    ROLE_CREATE,
    ROLE_DELETE,
    ROLE_READ,
    ROLE_UPDATE,
)
from app.modules.roles.models import Role
from app.modules.roles.schemas import (
    PermissionCatalogItem,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get(
    "/permissions",
    response_model=list[PermissionCatalogItem],
    summary="List every permission key in the system",
)
async def list_permission_catalog(
    _user=Depends(get_current_user),
) -> list[dict]:
    """Returns the catalog the frontend uses to render the permission matrix."""
    return PERMISSION_CATALOG


@router.get("", response_model=list[RoleRead])
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(ROLE_READ)),
) -> list[Role]:
    result = await db.execute(
        select(Role).where(Role.tenant_id == current_user.tenant_id).order_by(Role.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(ROLE_CREATE)),
) -> Role:
    role = Role(
        tenant_id=current_user.tenant_id,
        name=payload.name,
        description=payload.description,
        permissions=payload.permissions,
        is_system=False,
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return role


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(ROLE_READ)),
) -> Role:
    role = await _load_role(db, role_id, current_user.tenant_id)
    return role


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(ROLE_UPDATE)),
) -> Role:
    role = await _load_role(db, role_id, current_user.tenant_id)

    # System roles can have their permissions edited (so an admin can tighten
    # the "Operator" role) but not be renamed — keeps the UI consistent.
    if role.is_system and payload.name is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rename a system role",
        )

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.permissions is not None:
        role.permissions = payload.permissions

    await db.flush()
    await db.refresh(role)
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(ROLE_DELETE)),
) -> None:
    role = await _load_role(db, role_id, current_user.tenant_id)
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System roles cannot be deleted",
        )
    if role.users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role is assigned to {len(role.users)} user(s)",
        )
    await db.delete(role)


async def _load_role(db: AsyncSession, role_id: UUID, tenant_id: UUID) -> Role:
    result = await db.execute(
        select(Role)
        .where(Role.id == role_id, Role.tenant_id == tenant_id)
        .options(selectinload(Role.users))
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    return role
