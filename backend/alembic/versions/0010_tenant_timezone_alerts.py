"""Add tenants.timezone + alerts table

Revision ID: 0010_tenant_timezone_alerts
Revises: 0009_floor_plan_zones
Create Date: 2026-06-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_tenant_timezone_alerts"
down_revision: Union[str, None] = "0009_floor_plan_zones"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Tenant timezone. Existing rows get 'UTC' via server_default;
    #    operators set the real value via tenant admin UI later.
    op.add_column(
        "tenants",
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="UTC",
            nullable=False,
        ),
    )

    # 2) Alerts table.
    op.create_table(
        "alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_name", sa.String(length=120), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_kind", sa.String(length=32), nullable=False),
        sa.Column("rule_label", sa.String(length=120), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("condition_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "acknowledged_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "channels_attempted",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )

    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index(
        "ix_alerts_tenant_status_fired",
        "alerts",
        ["tenant_id", "status", "fired_at"],
    )
    op.create_index(
        "ix_alerts_tenant_zone_fired",
        "alerts",
        ["tenant_id", "zone_id", "fired_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_tenant_zone_fired", table_name="alerts")
    op.drop_index("ix_alerts_tenant_status_fired", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_index("ix_alerts_tenant_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_column("tenants", "timezone")
