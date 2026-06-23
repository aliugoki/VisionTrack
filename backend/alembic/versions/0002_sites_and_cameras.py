"""Add sites and cameras tables.

Revision ID: 0002_sites_and_cameras
Revises: 0001_initial
Create Date: 2026-01-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_sites_and_cameras"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- sites -----------------------------------------------------------------
    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Karachi"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_sites_tenant_id", "sites", ["tenant_id"])

    # -- cameras ---------------------------------------------------------------
    op.create_table(
        "cameras",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("rtsp_url", sa.String(2048), nullable=False),
        sa.Column("mediamtx_path", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("is_recording", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_change_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "calibration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "stream_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_cameras_tenant_name"),
        sa.UniqueConstraint("mediamtx_path", name="uq_cameras_mediamtx_path"),
    )
    op.create_index("ix_cameras_tenant_id", "cameras", ["tenant_id"])
    op.create_index("ix_cameras_site_id", "cameras", ["site_id"])
    op.create_index("ix_cameras_status", "cameras", ["status"])


def downgrade() -> None:
    op.drop_index("ix_cameras_status", table_name="cameras")
    op.drop_index("ix_cameras_site_id", table_name="cameras")
    op.drop_index("ix_cameras_tenant_id", table_name="cameras")
    op.drop_table("cameras")
    op.drop_index("ix_sites_tenant_id", table_name="sites")
    op.drop_table("sites")
