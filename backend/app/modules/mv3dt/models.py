"""MV3DT Phase A — global (cross-camera) track ORM models.

A GlobalTrack is one physical person's contiguous journey across the site,
stitched from per-camera `tracks` by the MultiViewFuser using floor-plan
world positions (+ optional appearance identity). See docs/MV3DT.md.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class GlobalTrack(Base):
    """A cross-camera journey. Distinct from Person (appearance identity):
    a person can have many global tracks over time; each global track groups
    the per-camera Track fragments of one continuous visit."""

    __tablename__ = "global_tracks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Appearance identity, when the matcher has attributed the fragments.
    person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
    )
    floor_plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("floor_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_global_tracks_tenant_time", "tenant_id", "started_at"),
    )


class GlobalTrackPoint(Base):
    """A fused world-frame position along a global track.

    Floor-plan fractional coords (0..1), averaged across the cameras seeing
    the person at that instant. Plain table (no TimescaleDB in this deploy).
    """

    __tablename__ = "global_track_points"

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    global_track_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    world_x: Mapped[float] = mapped_column(Float, nullable=False)
    world_y: Mapped[float] = mapped_column(Float, nullable=False)
    contributing_camera_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_global_track_points_track", "global_track_id"),
        Index("ix_global_track_points_tenant_ts", "tenant_id", "ts"),
    )
