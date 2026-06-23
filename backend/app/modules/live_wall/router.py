"""Live Wall REST endpoints.

  GET    /live-wall/presets        list all presets in tenant
  POST   /live-wall/presets        create new preset
  GET    /live-wall/presets/{id}   get one preset
  PATCH  /live-wall/presets/{id}   update fields (partial)
  DELETE /live-wall/presets/{id}   delete preset

Reading uses camera:stream_view (you can view the wall if you can view
the cameras in it). Creating/editing/deleting uses live_wall:manage_presets.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import CAMERA_STREAM_VIEW, LIVE_WALL_MANAGE_PRESETS
from app.modules.live_wall import service
from app.modules.live_wall.schemas import (
    WallPresetCreate,
    WallPresetRead,
    WallPresetUpdate,
)
from app.modules.live_wall.service import CameraNotInTenant, PresetNameConflict

router = APIRouter(prefix="/live-wall", tags=["live-wall"])


@router.get("/presets", response_model=list[WallPresetRead])
async def list_presets(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(CAMERA_STREAM_VIEW)),
):
    presets = await service.list_presets(db, current_user.tenant_id)
    return [WallPresetRead.model_validate(p) for p in presets]


@router.post(
    "/presets",
    response_model=WallPresetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_preset(
    payload: WallPresetCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(LIVE_WALL_MANAGE_PRESETS)),
):
    try:
        preset = await service.create_preset(
            db, current_user.tenant_id, current_user.id, payload
        )
    except PresetNameConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A preset named '{e.args[0]}' already exists",
        )
    except CameraNotInTenant as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Camera {e.camera_id} is not in this tenant",
        )
    await db.commit()
    return WallPresetRead.model_validate(preset)


@router.get("/presets/{preset_id}", response_model=WallPresetRead)
async def get_preset(
    preset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(CAMERA_STREAM_VIEW)),
):
    preset = await service.get_preset(db, current_user.tenant_id, preset_id)
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found"
        )
    return WallPresetRead.model_validate(preset)


@router.patch("/presets/{preset_id}", response_model=WallPresetRead)
async def update_preset(
    preset_id: UUID,
    payload: WallPresetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(LIVE_WALL_MANAGE_PRESETS)),
):
    try:
        preset = await service.update_preset(
            db, current_user.tenant_id, preset_id, payload
        )
    except PresetNameConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A preset named '{e.args[0]}' already exists",
        )
    except CameraNotInTenant as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Camera {e.camera_id} is not in this tenant",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found"
        )
    await db.commit()
    return WallPresetRead.model_validate(preset)


@router.delete(
    "/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_preset(
    preset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(LIVE_WALL_MANAGE_PRESETS)),
):
    deleted = await service.delete_preset(
        db, current_user.tenant_id, preset_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found"
        )
    await db.commit()
