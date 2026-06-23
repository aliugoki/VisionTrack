"""Track query service.

The consumer (consumer.py) writes data; this module reads it for the
REST endpoints. Keeping read and write paths separate makes it easier
to add a read replica in Phase 4 if/when query volume grows.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tracks.models import Track, TrackPoint


async def get_active_tracks(
    db: AsyncSession, tenant_id: UUID, camera_id: UUID | None = None
) -> list[Track]:
    """Return tracks that haven't ended yet, optionally filtered to one camera.

    "Active" = ended_at IS NULL AND started recently. We cap at 60 seconds
    of staleness so abandoned tracks (worker crashed mid-track) get filtered.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    stmt = (
        select(Track)
        .where(Track.tenant_id == tenant_id)
        .where(Track.ended_at.is_(None))
        .where(Track.updated_at >= cutoff)
        .order_by(Track.started_at.desc())
        .limit(500)
    )
    if camera_id is not None:
        stmt = stmt.where(Track.camera_id == camera_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_track_by_id(
    db: AsyncSession, tenant_id: UUID, track_id: UUID
) -> Track | None:
    result = await db.execute(
        select(Track).where(Track.id == track_id, Track.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_track_points(
    db: AsyncSession,
    tenant_id: UUID,
    track_id: UUID,
    limit: int = 10000,
) -> list[TrackPoint]:
    """Return every sampled point for one track, oldest first."""
    stmt = (
        select(TrackPoint)
        .where(TrackPoint.track_id == track_id)
        .where(TrackPoint.tenant_id == tenant_id)
        .order_by(TrackPoint.ts.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_tracks_by_time_range(
    db: AsyncSession,
    tenant_id: UUID,
    camera_id: UUID,
    start: datetime,
    end: datetime,
    limit: int = 500,
) -> list[Track]:
    """List tracks that overlap a time range on a specific camera."""
    stmt = (
        select(Track)
        .where(Track.tenant_id == tenant_id)
        .where(Track.camera_id == camera_id)
        .where(
            and_(
                Track.started_at <= end,
                # Either still active or ended after the range start
                ((Track.ended_at.is_(None)) | (Track.ended_at >= start)),
            )
        )
        .order_by(Track.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
