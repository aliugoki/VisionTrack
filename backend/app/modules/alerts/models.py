"""Alert ORM model.

One row per firing of a zone rule. Status starts as 'active' and moves
to 'acknowledged' (operator pressed ack) and then 'resolved' (either
manually or auto-resolved by the evaluator when the underlying
condition stops being true and the rearm window passes).

Why we don't FK zone_id / rule_id to real tables:
  Zones and rules live as JSONB on FloorPlan.zones (Step 5 Batch A
  decision — kept atomic-replace UX simple). The IDs we store are
  UUIDs the operator created in the editor, NOT FK references. If a
  zone is deleted, historical alerts remain queryable by name.

Index strategy:
  Most common query: "give me the recent active/unacked alerts for
  this tenant for the operator dashboard". Composite index on
  (tenant_id, status, fired_at desc) covers it.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Alert(Base):
    """One firing of a zone rule."""
    __tablename__ = "alerts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity of the (zone, rule) that fired. NOT foreign keys — see docstring.
    # We capture the names too so historical alerts read sensibly even after
    # the operator edits or deletes the zone.
    plan_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    zone_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    rule_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Severity matches the source rule. Indexed for dashboard filters.
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # The actual value at fire time — e.g. 7 people in a "max 5" zone.
    # Stored as float so we can also use it for dwell durations (seconds).
    condition_value: Mapped[float] = mapped_column(nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)

    # Lifecycle status: active → acknowledged → resolved.
    # Set by the evaluator on create. Updated by Batch E endpoints later.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )

    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Channels we attempted to dispatch on. Batch F populates this.
    # ["in_app"] always; ["in_app", "email", "whatsapp"] when configured.
    channels_attempted: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )

    # Free-form extra context — for debugging mostly. May include
    # camera IDs contributing to the count, snapshot URLs (later), etc.
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    __table_args__ = (
        # Dashboard query: recent unacked alerts for this tenant
        Index("ix_alerts_tenant_status_fired", "tenant_id", "status", "fired_at"),
        # Per-zone history queries (used in zone detail pages later)
        Index("ix_alerts_tenant_zone_fired", "tenant_id", "zone_id", "fired_at"),
    )
