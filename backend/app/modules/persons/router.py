"""Persons HTTP routes.

  GET /persons              List persons in tenant, paged
  GET /persons/{id}         One person + timeline

Persons are created by the internal matcher (P2.5), not via API.
This batch (P2.1) is read-only — the endpoints work but return
empty lists until the DeepStream pipeline begins emitting embeddings
and the matcher creates Person rows.

Permission required: TRACK_READ (no separate person:read for now —
persons are an aggregated view over tracks, so the existing track-read
permission is the natural gate).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import TRACK_READ
from app.modules.persons.schemas import FaceIdentity, PersonDetail, PersonRead
from app.modules.persons.service import (
    get_best_identity,
    get_identities_for,
    get_person,
    get_person_timeline,
    list_persons,
)
from app.modules.users.models import User


router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("", response_model=list[PersonRead])
async def list_persons_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(RequirePermission(TRACK_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> list[PersonRead]:
    rows = await list_persons(
        db,
        tenant_id=current_user.tenant_id,
        limit=limit,
        offset=offset,
    )
    idents = await get_identities_for(
        db,
        tenant_id=current_user.tenant_id,
        person_ids=[r.id for r in rows],
    )
    out: list[PersonRead] = []
    for r in rows:
        pr = PersonRead.model_validate(r)
        ident = idents.get(r.id)
        if ident is not None:
            pr.face_identity = FaceIdentity.model_validate(ident)
        out.append(pr)
    return out


@router.get("/{person_id}", response_model=PersonDetail)
async def get_person_endpoint(
    person_id: UUID,
    current_user: User = Depends(RequirePermission(TRACK_READ)),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> PersonDetail:
    person = await get_person(
        db, tenant_id=current_user.tenant_id, person_id=person_id
    )
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Person not found"
        )
    timeline = await get_person_timeline(
        db, tenant_id=current_user.tenant_id, person_id=person_id
    )
    ident = await get_best_identity(
        db, tenant_id=current_user.tenant_id, person_id=person_id
    )
    # PersonRead fields + timeline list
    return PersonDetail(
        id=person.id,
        tenant_id=person.tenant_id,
        first_seen_at=person.first_seen_at,
        last_seen_at=person.last_seen_at,
        appearance_count=person.appearance_count,
        created_at=person.created_at,
        face_identity=FaceIdentity.model_validate(ident) if ident else None,
        timeline=timeline,
    )
