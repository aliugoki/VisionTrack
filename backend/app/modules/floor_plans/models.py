"""Floor Plans module — ORM model.

A floor plan is a blueprint image belonging to a Site. One site can have
many floor plans (a factory has multiple buildings; a building has
multiple floors).

Storage layout:
  MinIO bucket: visiontrack-floor-plans
  Original file: tenants/{tenant_id}/sites/{site_id}/floor-plans/{plan_id}/original.{ext}
  Rendered PNG (PDFs only): same prefix + /rendered.png

The `width_px` / `height_px` columns store the image's source dimensions.
All future Batch D marker placements are stored as fractional coordinates
(0..1 relative to width/height) so they scale correctly when the viewer
is displayed at any size.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FloorPlan(Base):
    """A single blueprint belonging to a Site."""
    __tablename__ = "floor_plans"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Original file info (what the user uploaded)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    original_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Storage type: 'png', 'jpg', 'svg', 'pdf' — affects whether we have a
    # rendered.png companion file and how the viewer serves the image.
    format: Mapped[str] = mapped_column(String(10), nullable=False)

    # Source image pixel dimensions. For PDFs this is the rendered.png size;
    # for raster images this is the upload's native size; for SVGs we read
    # the viewBox if present, otherwise fall back to 1000x1000 (SVG is
    # vector — pixel dimensions are nominal anyway).
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)

    # MinIO object keys (relative paths within the bucket).
    storage_key_original: Mapped[str] = mapped_column(String(500), nullable=False)
    # Only set for PDF uploads (where we have a rendered.png companion).
    storage_key_rendered: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Camera marker placements. Array of MarkerSchema-shaped dicts.
    # Stored on the floor plan row itself (not a child table) because:
    #   - Always loaded/saved as a single set during editing
    #   - Small (rarely >100 markers per plan)
    #   - Atomic save semantics simplify the editor UX
    # Phase 3 calibration may split this out if per-marker metadata grows.
    markers: Mapped[list[dict]] = mapped_column(
        JSONB, default=list, nullable=False, server_default="[]"
    )

    # Polygon zones for occupancy / dwell / entry rules (Step 5).
    # Same JSONB-on-row rationale as markers above. Each zone has its own
    # rules array nested inside it. The Celery alert-evaluation task
    # (Step 5 Batch C) reads this column once per plan per evaluation tick.
    zones: Mapped[list[dict]] = mapped_column(
        JSONB, default=list, nullable=False, server_default="[]"
    )

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
        Index("ix_floor_plans_tenant_site", "tenant_id", "site_id"),
        Index("ix_floor_plans_tenant_name", "tenant_id", "name"),
    )
