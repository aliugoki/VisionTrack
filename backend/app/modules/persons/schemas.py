"""Pydantic schemas for the persons module.

Read-only this batch (P2.1). Write side (create/update/delete) is
done internally by the matcher in P2.5, not via this API.

Embeddings themselves (the 512-dim float arrays) are NEVER returned
to clients — they're internal data, expensive to serialize, and
contain no useful info for end users. The API exposes:
  - Person identity metadata (id, first_seen_at, etc.)
  - Per-track timeline (which camera, when, how long)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FaceIdentity(BaseModel):
    """External (face-recognition) identity correlated onto a person.

    Populated from `person_identities` (written by the face-identity consumer).
    A person may accumulate more than one candidate label from noisy
    correlation; the API surfaces the strongest one (most votes).
    """
    model_config = ConfigDict(from_attributes=True)

    emp_id: str
    name: str | None
    confidence: float
    votes: int
    last_labeled_at: datetime


class PersonRead(BaseModel):
    """Lightweight person identity, no embeddings."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    appearance_count: int
    created_at: datetime
    # Best external identity from the face-recognition feed, or null if this
    # cross-camera person has not been correlated to a recognized face yet.
    face_identity: FaceIdentity | None = None


class PersonTimelineEntry(BaseModel):
    """One row of a person's cross-camera timeline.

    Each entry is one track — i.e., one continuous presence on one
    camera. Multiple entries per person are expected (that's the whole
    point of cross-camera identity).
    """
    model_config = ConfigDict(from_attributes=True)

    track_id: UUID
    camera_id: UUID
    camera_name: str | None
    started_at: datetime
    ended_at: datetime | None
    point_count: int


class PersonDetail(PersonRead):
    """Person with their cross-camera timeline.

    Returned by GET /persons/{id}/timeline. The timeline is sorted
    DESC by started_at and is paginated implicitly (limit baked in
    at the service layer, default 100 entries).
    """
    timeline: list[PersonTimelineEntry]
