"""Tracks module — ORM models.

Two tables:

  tracks         — one row per (camera, track_id) pair. Lifecycle metadata:
                   started_at, ended_at, first_bbox, last_bbox, point_count.
                   ~50-500 rows/camera/day at typical foot traffic.

  track_points   — TimescaleDB hypertable. One row per frame *kept* (2 fps
                   sampling for storage; live broadcast remains at full 10
                   fps). Each row is a snapshot of one person at one moment.
                   ~170K rows/camera/day at 2 fps.

The hypertable is partitioned by `ts` with 1-day chunks. Retention is
enforced by TimescaleDB's drop_chunks policy (configured in the migration),
not by application code — it runs in the database and scales automatically.

Indexes:
  - track_points (track_id, ts) for "trail of one person" queries
  - track_points (camera_id, ts) for "everyone at camera X yesterday" queries
  - tracks (camera_id, started_at desc) for the live "active tracks" view
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    text,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Track(Base):
    """One pedestrian's path through one camera's field of view.

    Created when ByteTrack first emits a track_id; updated when the track
    ends (no detections for `lost_track_buffer` frames). The actual frame
    points live in `track_points`.
    """
    __tablename__ = "tracks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The ByteTrack ID from the AI worker. Stable within a camera's tracker
    # lifetime; collides across camera reboots. Unique IDs are the (id, ts)
    # tuple, not this number.
    tracker_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cross-camera identity assigned by the matcher (P2.5). NULL until the
    # matcher attributes this track to a Person. Column added in migration
    # 0013; declared here so the ORM (and persons.get_person_timeline, which
    # filters on it) can reference it.
    person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Cross-camera journey assigned by the MultiViewFuser (MV3DT Phase A).
    # NULL until this fragment is stitched into a global track. Column added
    # in migration 0016.
    global_track_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("global_tracks.id", ondelete="SET NULL"),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Snapshot of the first and most-recent bounding box. Useful for the
    # "active tracks" UI without having to query track_points.
    first_bbox: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_bbox: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # How many frame points we persisted. Note: live frame count is higher
    # — this only counts what we sampled into track_points.
    point_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_tracks_camera_started", "camera_id", "started_at"),
        Index("ix_tracks_tenant_active", "tenant_id", "ended_at"),
    )


class TrackPoint(Base):
    """One person's position at one moment in time.

    This table is a TimescaleDB hypertable — DO NOT add ForeignKey
    constraints from this table to other tables. TimescaleDB chunks
    must be self-contained for chunk pruning to work efficiently.

    The (track_id, ts) tuple is the natural primary key. We declare ts
    as the partition column in the migration.
    """
    __tablename__ = "track_points"

    # No id PK — hypertables work best without surrogate keys.
    # Composite PK is (ts, track_id) so chunk pruning is fast.
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    track_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, nullable=False
    )

    # Denormalized for chunk-local queries. No FK — see class docstring.
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    camera_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tracker_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Bounding box in source pixel space. We store as four floats rather
    # than JSONB so range queries on bbox_x1/bbox_y1 are usable for
    # heatmap aggregation in Phase 2 analytics.
    bbox_x1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x2: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y2: Mapped[float] = mapped_column(Float, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Reserved for Phase 3 (multi-view fusion). NULL until the camera has
    # a calibration matrix. Stored as floats so we can do floor-plan
    # range queries cheaply.
    world_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    world_y: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_track_points_camera_ts", "camera_id", text("ts DESC")),
        Index("ix_track_points_track_ts", "track_id", text("ts DESC")),
        Index("ix_track_points_tenant_ts", "tenant_id", text("ts DESC")),
    )
