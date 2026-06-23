"""Role and user-role association models.

A Role is a named bag of permission strings (e.g. {"camera:read",
"alert:acknowledge"}). Roles are scoped to tenants — each tenant has
its own set of roles, seeded with four defaults (Tenant Admin,
Supervisor, Operator, Viewer) that can be customised or cloned.

is_system roles cannot be deleted (only their permissions edited).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


# Many-to-many between users and roles.
# Composite primary key on (user_id, role_id) prevents duplicate assignments.
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        PG_UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "assigned_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
)


class Role(Base):
    __tablename__ = "roles"

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, nullable=False
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="roles")  # type: ignore  # noqa: F821
    users: Mapped[list["User"]] = relationship(  # type: ignore  # noqa: F821
        secondary=user_roles, back_populates="roles"
    )
