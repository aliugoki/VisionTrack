"""Employees module — ORM model.

The employee roster is **sourced from FaceTrack** (the face-recognition system):
``scripts/sync_facetrack_employees.py`` reads FaceTrack's ``user_data`` table and
upserts rows here. ``emp_id`` is the shared key the face-identity bridge stamps
onto ``person_identities``, so an employee here links to their tracked identity.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Shared key with the face pipeline / person_identities.
    emp_id: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # FaceTrack's company_id (its multi-tenant key) for reference.
    external_company_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="facetrack")
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "emp_id", name="uq_employee_tenant_emp"),
    )
