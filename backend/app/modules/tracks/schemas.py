"""Tracks module — Pydantic read schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TrackRead(BaseModel):
    """A pedestrian track. Returned from /tracks/active and /tracks/{id}."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    camera_id: UUID
    tracker_id: int
    started_at: datetime
    ended_at: datetime | None
    first_bbox: dict[str, Any]
    last_bbox: dict[str, Any]
    point_count: int

    @property
    def duration_seconds(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()


class TrackPointRead(BaseModel):
    """One sampled frame from a track."""
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    track_id: UUID
    camera_id: UUID
    tracker_id: int
    bbox: list[float]  # [x1, y1, x2, y2]
    confidence: float

    @classmethod
    def from_orm_row(cls, p) -> "TrackPointRead":
        """Construct from a TrackPoint ORM row, flattening the bbox fields."""
        return cls(
            ts=p.ts,
            track_id=p.track_id,
            camera_id=p.camera_id,
            tracker_id=p.tracker_id,
            bbox=[p.bbox_x1, p.bbox_y1, p.bbox_x2, p.bbox_y2],
            confidence=p.confidence,
        )


class LiveTrackEvent(BaseModel):
    """One Socket.IO message — a snapshot of all current detections.

    Emitted at the full 10 fps (not sampled), one per camera per frame.
    The frontend overlay uses these to draw bounding boxes synchronized
    to the video timecode.
    """
    type: str = "track_update"
    camera_id: UUID
    frame_ts_ms: int
    tracks: list[dict[str, Any]]  # each: {track_id, bbox, confidence, class_id}
