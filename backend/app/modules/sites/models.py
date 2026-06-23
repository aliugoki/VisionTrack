"""Site model — a physical location (factory, warehouse, office building).

Cameras and floor plans belong to a Site. A tenant can have one or many
sites. For the pilot most clients will have just one, but we model this
properly from day one — adding it later would require renaming every
camera and floor plan, and that's never fun.

Note on `attributes` column:
  Previously named `metadata` but renamed in migration 0003 because
  `metadata` shadows SQLAlchemy's `Base.metadata` attribute, which
  caused subtle ORM bugs. The DB column is now `attributes`.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Karachi", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Free-form site attributes (capacity, operating hours, custom tags).
    # Stored as JSONB so we can query individual keys later if needed.
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False, server_default="{}"
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

    cameras: Mapped[list["Camera"]] = relationship(  # type: ignore  # noqa: F821
        back_populates="site", cascade="all, delete-orphan"
    )
