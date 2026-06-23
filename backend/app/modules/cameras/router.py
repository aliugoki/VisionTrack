"""Cameras HTTP routes.

Endpoints:
  GET    /cameras                   List cameras (filterable)
  POST   /cameras                   Create a camera (+ register with MediaMTX)
  GET    /cameras/{id}              Read one
  PATCH  /cameras/{id}              Update (+ resync MediaMTX if source changed)
  PUT    /cameras/{id}/calibration  Set BEV homography (image -> floor plan)
  DELETE /cameras/{id}              Delete (+ unregister from MediaMTX)
  POST   /cameras/discover          ONVIF WS-Discovery probe on the LAN
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import (
    CAMERA_CALIBRATE,
    CAMERA_CREATE,
    CAMERA_DELETE,
    CAMERA_READ,
    CAMERA_UPDATE,
)
from app.modules.cameras import onvif_discovery, service
from app.modules.cameras.schemas import (
    CameraCalibration,
    CameraCreate,
    CameraDiscoveryRequest,
    CameraDiscoveryResult,
    CameraRead,
    CameraUpdate,
)

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraRead])
async def list_cameras(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(CAMERA_READ)),
    site_id: UUID | None = Query(None, description="Filter by site"),
    status: str | None = Query(None, description="Filter by status"),
    search: str | None = Query(None, description="Search by name substring"),
):
    cameras = await service.list_cameras(
        db,
        tenant_id=current_user.tenant_id,
        site_id=site_id,
        status_filter=status,
        search=search,
    )
    # Enrich with floor-plan placements so the UI can show "on N floor
    # plans" badges and offer click-through to the plan view. Single
    # query for all plans in the tenant — no N+1 across cameras.
    locations_map = await service.get_floor_plan_locations_for_tenant(
        db, current_user.tenant_id
    )
    # Attach as a transient attribute on each ORM object; Pydantic's
    # `from_attributes=True` will pick it up on serialization. The DB
    # never sees this attribute since it isn't a mapped column.
    for cam in cameras:
        cam.floor_plan_locations = locations_map.get(cam.id, [])  # type: ignore[attr-defined]
    return cameras


@router.post("", response_model=CameraRead, status_code=status.HTTP_201_CREATED)
async def create_camera(
    payload: CameraCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(CAMERA_CREATE)),
):
    return await service.create_camera(db, current_user.tenant_id, payload)


@router.get("/{camera_id}", response_model=CameraRead)
async def get_camera(
    camera_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(CAMERA_READ)),
):
    return await service._load_camera(db, camera_id, current_user.tenant_id)


@router.patch("/{camera_id}", response_model=CameraRead)
async def update_camera(
    camera_id: UUID,
    payload: CameraUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(CAMERA_UPDATE)),
):
    return await service.update_camera(
        db, current_user.tenant_id, camera_id, payload
    )


@router.put("/{camera_id}/calibration", response_model=CameraRead)
async def set_camera_calibration(
    camera_id: UUID,
    payload: CameraCalibration,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(CAMERA_CALIBRATE)),
):
    """Store the Bird's-Eye-View homography for a camera (image->floor plan)."""
    return await service.set_calibration(
        db, current_user.tenant_id, camera_id, payload
    )


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(RequirePermission(CAMERA_DELETE)),
):
    await service.delete_camera(db, current_user.tenant_id, camera_id)


@router.post(
    "/discover",
    response_model=list[CameraDiscoveryResult],
    summary="Probe the LAN for ONVIF cameras",
    description=(
        "Sends a WS-Discovery multicast probe to find ONVIF-compliant cameras "
        "on the local network. **Requires the backend container to be on the "
        "same L2 broadcast domain as the cameras** \u2014 usually via "
        "`network_mode: host` in docker-compose. Returns an empty list if "
        "discovery isn't reachable in the current network setup."
    ),
)
async def discover_cameras(
    payload: CameraDiscoveryRequest,
    _user=Depends(RequirePermission(CAMERA_CREATE)),
):
    return await onvif_discovery.discover_cameras(
        timeout_seconds=payload.timeout_seconds,
        username=payload.username,
        password=payload.password,
    )
