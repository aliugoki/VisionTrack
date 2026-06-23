"""Persons query layer.

Read-only this batch. All queries scope to tenant_id from JWT.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cameras.models import Camera
from app.modules.persons.models import Person, PersonIdentity
from app.modules.tracks.models import Track


# Soft cap on per-person timeline rows. The UI paginates; this is the
# upper bound for a single response. Persons with >100 tracks are rare
# enough (one person spending an entire shift visible).
TIMELINE_MAX_ROWS = 100


async def list_persons(
    db: AsyncSession, *, tenant_id: UUID, limit: int = 50, offset: int = 0
) -> list[Person]:
    """List persons in the current tenant, most-recently-seen first."""
    q = (
        select(Person)
        .where(Person.tenant_id == tenant_id)
        .order_by(Person.last_seen_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_person(
    db: AsyncSession, *, tenant_id: UUID, person_id: UUID
) -> Person | None:
    """Fetch one person by id, scoped to tenant."""
    q = select(Person).where(
        Person.id == person_id, Person.tenant_id == tenant_id
    )
    result = await db.execute(q)
    return result.scalar_one_or_none()


# "Strongest" identity = most votes, then highest confidence, then most recent.
_IDENTITY_ORDER = (
    PersonIdentity.votes.desc(),
    PersonIdentity.confidence.desc(),
    PersonIdentity.last_labeled_at.desc(),
)


async def get_best_identity(
    db: AsyncSession, *, tenant_id: UUID, person_id: UUID
) -> PersonIdentity | None:
    """The strongest face-identity label for one person, or None."""
    q = (
        select(PersonIdentity)
        .where(
            PersonIdentity.tenant_id == tenant_id,
            PersonIdentity.person_id == person_id,
        )
        .order_by(*_IDENTITY_ORDER)
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def get_identities_for(
    db: AsyncSession, *, tenant_id: UUID, person_ids: list[UUID]
) -> dict[UUID, PersonIdentity]:
    """Batch the strongest identity per person (avoids N+1 in list views)."""
    if not person_ids:
        return {}
    q = (
        select(PersonIdentity)
        .where(
            PersonIdentity.tenant_id == tenant_id,
            PersonIdentity.person_id.in_(person_ids),
        )
        .order_by(*_IDENTITY_ORDER)
    )
    best: dict[UUID, PersonIdentity] = {}
    for ident in (await db.execute(q)).scalars().all():
        # First row per person wins thanks to the ordering above.
        if ident.person_id is not None and ident.person_id not in best:
            best[ident.person_id] = ident
    return best


async def get_person_timeline(
    db: AsyncSession, *, tenant_id: UUID, person_id: UUID
) -> list[dict]:
    """Get the cross-camera timeline for a person.

    Returns a list of dicts shaped like PersonTimelineEntry. Each
    dict corresponds to one Track row attributed to this person.
    Joined with Camera for the human-readable name.

    Sorted by started_at DESC (most recent first). Capped at
    TIMELINE_MAX_ROWS.
    """
    q = (
        select(
            Track.id.label("track_id"),
            Track.camera_id,
            Camera.name.label("camera_name"),
            Track.started_at,
            Track.ended_at,
            Track.point_count,
        )
        .join(Camera, Camera.id == Track.camera_id, isouter=True)
        .where(
            Track.tenant_id == tenant_id,
            Track.person_id == person_id,
        )
        .order_by(Track.started_at.desc())
        .limit(TIMELINE_MAX_ROWS)
    )
    result = await db.execute(q)
    rows = result.all()
    return [
        {
            "track_id": r.track_id,
            "camera_id": r.camera_id,
            "camera_name": r.camera_name,
            "started_at": r.started_at,
            "ended_at": r.ended_at,
            "point_count": r.point_count,
        }
        for r in rows
    ]
