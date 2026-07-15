"""Tenant model.

Every tenant is an isolated client account. All other entities reference
their tenant via tenant_id. Subdomain is used for future routing
(e.g. acme.visiontrack.io) — unique across the whole system.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, String, func, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[str] = mapped_column(
        String(63), nullable=False, unique=True, index=True
    )
    plan: Mapped[str] = mapped_column(String(50), default="trial", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recording_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    # IANA timezone name (e.g. "Asia/Karachi", "Asia/Riyadh", "Asia/Dubai").
    # Used by the alert evaluator to determine whether scheduled rules are
    # currently active. Default "UTC" — operators must set this explicitly
    # via the tenant admin UI when they create the tenant. Validation
    # happens at the schema layer (zoneinfo.ZoneInfo() round-trip).
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="UTC", default="UTC"
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict, nullable=False)
    # Feature flag added in migration 0013 — declared here so it's selected and
    # TenantRead can serialize it (otherwise /tenants/me 500s on a missing attr).
    use_deepstream: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
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

    # Reverse relationships — declared as strings to avoid circular imports
    users: Mapped[list["User"]] = relationship(  # type: ignore  # noqa: F821
        back_populates="tenant", cascade="all, delete-orphan"
    )
    roles: Mapped[list["Role"]] = relationship(  # type: ignore  # noqa: F821
        back_populates="tenant", cascade="all, delete-orphan"
    )
