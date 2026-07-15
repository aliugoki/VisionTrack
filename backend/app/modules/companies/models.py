"""Companies module — ORM model.

A "company" mirrors FaceTrack's company (its multi-tenant client). Reflected rows
carry ``source='facetrack'`` and an ``external_id`` (FaceTrack's company_id);
VisionTrack-native companies have ``source='visiontrack'`` and a NULL
``external_id``. Employees link to a company via ``external_company_id`` =
``external_id``. Secrets (passwords / tokens / api keys) are never copied.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # FaceTrack company_id for reflected rows; NULL for VisionTrack-native ones.
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    admin_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="facetrack")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", default=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # Non-null external_id unique per tenant (NULLs are distinct in Postgres,
        # so multiple VisionTrack-native companies are allowed).
        UniqueConstraint("tenant_id", "external_id", name="uq_company_tenant_external"),
    )
