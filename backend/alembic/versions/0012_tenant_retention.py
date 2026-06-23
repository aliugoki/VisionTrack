"""tenant recording retention

Revision ID: 0012_tenant_retention
Revises: 0011_recordings
Create Date: 2026-06-06 17:00:00

Adds a per-tenant retention policy column to the tenants table.

Default 30 days mirrors the MediaMTX recordDeleteAfter default already
in the config, so DB rows and on-disk files expire in lockstep.
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_tenant_retention"
down_revision = "0011_recordings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "recording_retention_days",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "recording_retention_days")
