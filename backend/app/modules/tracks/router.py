"""Tracks module — REST endpoints.

Read-only. Track data is created by the Redis consumer
(see app.modules.tracks.consumer) which runs as a background task on
backend startup.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import TRACK_READ
from app.modules.tracks import service
from app.modules.tracks.schemas import TrackPointRead, TrackRead

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("/active", response_model=list[TrackRead])
async def list_active_tracks(
    camera_id: Annotated[UUID | None, Query(description="Filter to one camera")] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(TRACK_READ)),
):
    """Tracks that are currently being detected (ended_at is NULL, recently updated).

    Use this on the Live Wall to show "who's in view right now". For
    historical replay use /tracks/by-time-range.
    """
    tracks = await service.get_active_tracks(
        db, tenant_id=current_user.tenant_id, camera_id=camera_id
    )
    return [TrackRead.model_validate(t) for t in tracks]


@router.get("/by-time-range", response_model=list[TrackRead])
async def list_tracks_by_time_range(
    camera_id: Annotated[UUID, Query(description="Required: which camera")],
    start: Annotated[datetime, Query(description="ISO-8601 start of range")],
    end: Annotated[datetime, Query(description="ISO-8601 end of range")],
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(TRACK_READ)),
):
    """All tracks that overlap [start, end] on the specified camera.

    "Overlap" means the track's started_at <= end AND
    (track's ended_at >= start OR track is still active).
    """
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be after start",
        )

    tracks = await service.get_tracks_by_time_range(
        db,
        tenant_id=current_user.tenant_id,
        camera_id=camera_id,
        start=start,
        end=end,
    )
    return [TrackRead.model_validate(t) for t in tracks]


@router.get("/{track_id}", response_model=TrackRead)
async def get_track(
    track_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(TRACK_READ)),
):
    track = await service.get_track_by_id(db, current_user.tenant_id, track_id)
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Track not found"
        )
    return TrackRead.model_validate(track)


@router.get("/{track_id}/points", response_model=list[TrackPointRead])
async def get_track_points(
    track_id: UUID,
    limit: Annotated[int, Query(ge=1, le=50000)] = 10000,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission(TRACK_READ)),
):
    """Return every sampled point for a track, oldest first.

    Used by the floor-plan replay and the track-trail overlay. Points are
    sampled at 2 fps so a 5-minute track returns ~600 points.
    """
    # First verify track is visible to this tenant
    track = await service.get_track_by_id(db, current_user.tenant_id, track_id)
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Track not found"
        )

    points = await service.get_track_points(
        db, tenant_id=current_user.tenant_id, track_id=track_id, limit=limit
    )
    return [TrackPointRead.from_orm_row(p) for p in points]
