"""Sites HTTP routes — minimal CRUD scoped to current tenant.

Sites need to exist before cameras can be created. We seed a default
"Main Site" on first run so the dashboard is usable immediately.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import (
    SITE_CREATE,
    SITE_DELETE,
    SITE_READ,
    SITE_UPDATE,
)
from app.modules.cameras.models import Camera
from app.modules.sites.models import Site
from app.modules.sites.schemas import SiteCreate, SiteRead, SiteUpdate

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteRead])
async def list_sites(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(SITE_READ)),
):
    # Sites + camera counts in a single round trip
    stmt = (
        select(Site, func.count(Camera.id).label("camera_count"))
        .outerjoin(Camera, Camera.site_id == Site.id)
        .where(Site.tenant_id == current_user.tenant_id)
        .group_by(Site.id)
        .order_by(Site.name)
    )
    result = await db.execute(stmt)
    sites: list[SiteRead] = []
    for site, camera_count in result.all():
        read = SiteRead.model_validate(site)
        read.camera_count = int(camera_count or 0)
        sites.append(read)
    return sites


@router.post("", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
async def create_site(
    payload: SiteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(SITE_CREATE)),
):
    dup = await db.execute(
        select(Site).where(
            Site.tenant_id == current_user.tenant_id, Site.name == payload.name
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A site with this name already exists",
        )
    site = Site(
        tenant_id=current_user.tenant_id,
        name=payload.name,
        address=payload.address,
        timezone=payload.timezone,
    )
    db.add(site)
    await db.flush()
    await db.refresh(site)
    out = SiteRead.model_validate(site)
    out.camera_count = 0
    return out


@router.get("/{site_id}", response_model=SiteRead)
async def get_site(
    site_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(SITE_READ)),
):
    site = await _load_site(db, site_id, current_user.tenant_id)
    count_q = await db.execute(
        select(func.count(Camera.id)).where(Camera.site_id == site.id)
    )
    out = SiteRead.model_validate(site)
    out.camera_count = int(count_q.scalar_one() or 0)
    return out


@router.patch("/{site_id}", response_model=SiteRead)
async def update_site(
    site_id: UUID,
    payload: SiteUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(SITE_UPDATE)),
):
    site = await _load_site(db, site_id, current_user.tenant_id)
    if payload.name is not None:
        site.name = payload.name
    if payload.address is not None:
        site.address = payload.address
    if payload.timezone is not None:
        site.timezone = payload.timezone
    if payload.is_active is not None:
        site.is_active = payload.is_active
    await db.flush()
    await db.refresh(site)
    count_q = await db.execute(
        select(func.count(Camera.id)).where(Camera.site_id == site.id)
    )
    out = SiteRead.model_validate(site)
    out.camera_count = int(count_q.scalar_one() or 0)
    return out


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(SITE_DELETE)),
):
    site = await _load_site(db, site_id, current_user.tenant_id)
    # Block delete if cameras exist — safer than cascading
    count_q = await db.execute(
        select(func.count(Camera.id)).where(Camera.site_id == site.id)
    )
    n = int(count_q.scalar_one() or 0)
    if n > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site has {n} camera(s) attached; remove them first",
        )
    await db.delete(site)


async def _load_site(db: AsyncSession, site_id: UUID, tenant_id: UUID) -> Site:
    result = await db.execute(
        select(Site).where(Site.id == site_id, Site.tenant_id == tenant_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Site not found"
        )
    return site
