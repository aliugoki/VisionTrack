"""Live Wall preset model.

A preset is a named layout: grid size + which camera goes in which tile.
Presets are scoped per-tenant (shared across all users in the tenant).

The `tiles` field is a JSONB array of camera_id entries indexed by tile
position. Position is `row * cols + col`. An entry can be a UUID string
(camera assigned) or null (empty tile). e.g. for a 2×2 with cameras in
top-left and bottom-right:

  [
    "abc...",   // position 0 (row 0, col 0)
    null,       // position 1 (row 0, col 1)
    null,       // position 2 (row 1, col 0)
    "def..."    // position 3 (row 1, col 1)
  ]

We store as JSONB rather than a child table because:
  - Presets are small (max 16 entries)
  - Always read whole, never partial-updated
  - Operator UX is "drag a camera into a slot, save the whole layout"
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WallPreset(Base):
    """A named camera-grid configuration, shared within a tenant."""
    __tablename__ = "wall_presets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # User who created/last-modified — informational only, doesn't affect access.
    # Presets are tenant-shared so any user with the right permission can edit.
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Grid dimensions. 1x1, 2x2, 3x3, 4x4 — both columns are equal in the
    # supported set, but we store separately for forward-compat if/when we
    # add asymmetric layouts (e.g. 2x3 spotlight modes) in a later batch.
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    cols: Mapped[int] = mapped_column(Integer, nullable=False)

    # tiles[i] = camera_id (UUID str) or null. Length must equal rows*cols.
    tiles: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    # Optional metadata; reserved for future "default preset on login" / etc.
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)

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
        # Names must be unique within a tenant — operators don't want
        # two "Day Shift" presets to choose from.
        UniqueConstraint("tenant_id", "name", name="uq_wall_presets_tenant_name"),
        Index("ix_wall_presets_tenant_default", "tenant_id", "is_default"),
    )
