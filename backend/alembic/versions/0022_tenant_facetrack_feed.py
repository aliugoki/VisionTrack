"""tenants.facetrack_feed_enabled — per-tenant FaceTrack feed toggle

Revision ID: 0022_tenant_facetrack_feed
Revises: 0021_platform_admin
Create Date: 2026-07-16

Per-tenant switch controlling this tenant's FaceTrack integration:
  * the live face-identity feed (the Redis consumer that ingests recognitions
    into person_identities), and
  * the roster sync scripts (companies/employees), which skip disabled tenants.

Defaults to true so existing tenants keep their current (always-on) behaviour.
The global env gate FACE_IDENTITY_ENABLED still acts as the master switch.

Rollback: downgrade() drops the column.
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_tenant_facetrack_feed"
down_revision = "0021_platform_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "facetrack_feed_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "facetrack_feed_enabled")
